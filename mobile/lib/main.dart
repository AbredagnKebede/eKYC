import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:signature/signature.dart';
import 'package:uuid/uuid.dart';

import 'api/ekyc_api.dart';
import 'l10n/strings.dart';
import 'theme.dart';

const kDefaultApiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'https://ekyc-api-jj0j.onrender.com',
);

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.dark);
  runApp(const EkycApp());
}

class EkycApp extends StatelessWidget {
  const EkycApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Fayda Onboard',
      debugShowCheckedModeBanner: false,
      theme: buildEkycTheme(),
      home: const OnboardingShell(),
    );
  }
}

enum StepId {
  welcome,
  bank,
  consent,
  fayda,
  otp,
  liveness,
  fields,
  sign,
  status,
  done,
}

class OnboardingShell extends StatefulWidget {
  const OnboardingShell({super.key});

  @override
  State<OnboardingShell> createState() => _OnboardingShellState();
}

class _OnboardingShellState extends State<OnboardingShell> {
  late EkycApi api;
  String apiBase = kDefaultApiBase;
  String? deviceFp;
  StepId step = StepId.welcome;
  bool busy = false;
  String? error;
  String bankQuery = '';
  String locale = 'en';
  String? userRef;
  bool showPassport = false;
  List<Map<String, dynamic>> myApps = [];
  String selectedTier = 'standard';
  List<String> availableTiers = const ['standard'];
  Map<String, dynamic>? selectedBankSchema;

  S get s => S(locale);

  List<Map<String, dynamic>> banks = [];
  String? bankId;
  String? bankName;
  String? appId;
  String? txId;
  String fin = '';
  String otp = '';
  double? livenessScore;
  final incomeCtrl = TextEditingController(text: '15000');
  final occupationCtrl = TextEditingController(text: 'Software Engineer');
  String sourceOfFunds = 'Salary';
  final branchCtrl = TextEditingController();
  String? accountNumber;
  String? statusText;
  String? activationMsg;

  late final SignatureController sigCtrl;

  @override
  void initState() {
    super.initState();
    sigCtrl = SignatureController(
      penStrokeWidth: 2.2,
      penColor: EkycColors.navy,
      exportBackgroundColor: Colors.white,
    );
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final prefs = await SharedPreferences.getInstance();
    apiBase = prefs.getString('api_base') ?? kDefaultApiBase;
    locale = prefs.getString('locale') ?? 'en';
    userRef = prefs.getString('user_ref');
    var fp = prefs.getString('device_fp');
    if (fp == null || fp.isEmpty) {
      fp = sha256.convert(utf8.encode('dev-${const Uuid().v4()}')).toString().substring(0, 32);
      await prefs.setString('device_fp', fp);
    }
    deviceFp = fp;
    api = EkycApi(baseUrl: apiBase, deviceFingerprint: fp);
    final savedToken = prefs.getString('token');
    if (savedToken != null && savedToken.isNotEmpty) {
      api.token = savedToken;
    }
    if (userRef != null && userRef!.isNotEmpty) {
      try {
        await api.openDeviceSession(userRef!);
        await prefs.setString('token', api.token ?? '');
        await _refreshPassport();
        showPassport = myApps.isNotEmpty;
      } catch (_) {
        // cold start without server is fine
      }
    }
    setState(() {});
  }

  Future<void> _persistSession() async {
    final prefs = await SharedPreferences.getInstance();
    if (userRef != null) await prefs.setString('user_ref', userRef!);
    if (api.token != null) await prefs.setString('token', api.token!);
    await prefs.setString('locale', locale);
  }

  Future<void> _refreshPassport() async {
    if (userRef == null) return;
    myApps = await api.listApplications();
  }

  StepId _stepFromResume(String resume) {
    switch (resume) {
      case 'consent':
        return StepId.consent;
      case 'fayda':
        return StepId.fayda;
      case 'otp':
        return StepId.otp;
      case 'liveness':
        return StepId.liveness;
      case 'fields':
        return StepId.fields;
      case 'sign':
        return StepId.sign;
      case 'status':
        return StepId.status;
      case 'done':
        return StepId.done;
      case 'expired':
        return StepId.done;
      default:
        return StepId.welcome;
    }
  }

  Future<void> _resumeApp(Map<String, dynamic> row) async {
    await _run(() async {
      appId = row['application_id']?.toString();
      bankId = row['bank_id']?.toString();
      bankName = bankId;
      selectedTier = row['tier']?.toString() ?? 'standard';
      accountNumber = row['account_number']?.toString();
      statusText = row['status']?.toString();
      final resume = row['resume_step']?.toString() ?? 'welcome';
      if (resume == 'expired') {
        throw Exception(s.t('error.expired'));
      }
      showPassport = false;
      step = _stepFromResume(resume);
      if (step == StepId.status) {
        await _pollStatus();
      }
      if (step == StepId.done && statusText == 'ACCOUNT_OPENED' && accountNumber != null) {
        // stay on done-like status activate path
        step = StepId.status;
      }
    });
  }

  Future<void> _saveApiBase(String value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('api_base', value);
    setState(() {
      apiBase = value;
      api = EkycApi(baseUrl: value, deviceFingerprint: deviceFp!);
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await action();
      await _persistSession();
    } on EkycApiException catch (e) {
      final msg = (e.statusCode == 429 || e.statusCode == 410)
          ? s.t('otp.lockout')
          : e.message;
      setState(() => error = msg);
    } catch (e) {
      setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _loadBanksAndStart() async {
    await _run(() async {
      final raw = await api.listBanks();
      banks = raw.cast<Map<String, dynamic>>();
      banks.sort((a, b) => (a['bank_name'] as String).compareTo(b['bank_name'] as String));
      if (banks.isEmpty) throw Exception('No partner banks available');
      setState(() => step = StepId.bank);
    });
  }

  Future<void> _selectBank(Map<String, dynamic> bank) async {
    await _run(() async {
      bankId = bank['bank_id'] as String;
      bankName = bank['bank_name'] as String? ?? bankId;
      userRef ??= "usr_${deviceFp!.substring(0, 10)}";
      final tiers = (bank['supported_tiers'] as List?)?.map((e) => e.toString()).toList() ?? ['standard'];
      availableTiers = tiers.isEmpty ? ['standard'] : tiers;
      selectedTier = availableTiers.contains('standard') ? 'standard' : availableTiers.first;
      final byTier = bank['schemas_by_tier'];
      if (byTier is Map && byTier[selectedTier] is Map) {
        selectedBankSchema = Map<String, dynamic>.from(byTier[selectedTier] as Map);
      } else {
        selectedBankSchema = bank['dynamic_schema'] is Map
            ? Map<String, dynamic>.from(bank['dynamic_schema'] as Map)
            : null;
      }
      setState(() => step = StepId.consent);
      // Tier picked on next micro-step via dialog before create
      final tier = await _pickTier();
      if (tier == null) {
        setState(() => step = StepId.bank);
        return;
      }
      selectedTier = tier;
      final created = await api.createApplication(
        userRef: userRef!,
        bankId: bankId!,
        tier: selectedTier,
      );
      appId = created['application_id'] as String;
      setState(() => step = StepId.consent);
    });
  }

  Future<String?> _pickTier() async {
    if (!mounted) return selectedTier;
    return showModalBottomSheet<String>(
      context: context,
      backgroundColor: EkycColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(s.t('tier.title'), style: Theme.of(ctx).textTheme.titleLarge),
                const SizedBox(height: 12),
                for (final t in availableTiers)
                  ListTile(
                    title: Text(t),
                    trailing: t == selectedTier ? const Icon(Icons.check, color: EkycColors.teal) : null,
                    onTap: () => Navigator.pop(ctx, t),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _consent(bool accepted) async {
    await _run(() async {
      final res = await api.consent(appId!, accepted: accepted);
      if (!accepted) {
        setState(() {
          step = StepId.done;
          statusText = res['status'] as String?;
          activationMsg = 'Consent declined. No personal data was sent.';
        });
        return;
      }
      setState(() => step = StepId.fayda);
    });
  }

  Future<void> _startOtp() async {
    await _run(() async {
      final digits = fin.replaceAll(RegExp(r'\D'), '');
      final res = await api.startIdentity(appId!, digits);
      txId = res['transaction_id'] as String;
      setState(() => step = StepId.otp);
    });
  }

  Future<void> _verifyOtp() async {
    await _run(() async {
      await api.verifyOtp(appId!, txId!, otp.trim());
      setState(() => step = StepId.liveness);
    });
  }

  Future<void> _captureLiveness() async {
    await _run(() async {
      final picker = ImagePicker();
      final shot = await picker.pickImage(
        source: ImageSource.camera,
        preferredCameraDevice: CameraDevice.front,
        imageQuality: 85,
        maxWidth: 960,
      );
      if (shot == null) throw Exception('Camera capture cancelled');
      final bytes = await shot.readAsBytes();
      final res = await api.liveness(appId!, base64Encode(bytes));
      livenessScore = (res['liveness_score'] as num?)?.toDouble();
      setState(() => step = StepId.fields);
    });
  }

  Future<void> _saveFields() async {
    await _run(() async {
      final fields = <String, dynamic>{
        'monthly_income_etb': double.parse(incomeCtrl.text.trim()),
        'occupation': occupationCtrl.text.trim(),
        'source_of_funds': sourceOfFunds,
      };
      if (branchCtrl.text.trim().isNotEmpty) {
        fields['branch_code'] = branchCtrl.text.trim();
      }
      await api.saveDetails(appId!, fields);
      setState(() => step = StepId.sign);
    });
  }

  Future<void> _submit() async {
    await _run(() async {
      if (sigCtrl.isEmpty) throw Exception('Please sign before submitting');
      final png = await sigCtrl.toPngBytes();
      if (png == null || png.isEmpty) throw Exception('Could not export signature');
      await api.submit(appId!, base64Encode(png));
      setState(() => step = StepId.status);
      await _pollStatus();
    });
  }

  Future<void> _pollStatus() async {
    for (var i = 0; i < 90; i++) {
      final data = await api.getApplication(appId!);
      statusText = data['status'] as String?;
      accountNumber = data['account_number'] as String?;
      setState(() {});
      if (statusText == 'ACCOUNT_OPENED' && accountNumber != null) return;
      if (statusText == 'BANK_REJECTED') {
        throw Exception('Bank rejected the application');
      }
      // PENDING_REVIEW / SUBMITTED_TO_BANK: keep waiting for webhook or ops
      await Future<void>.delayed(const Duration(milliseconds: 700));
    }
    // Leave user on status screen instead of hard-failing — Passport can resume.
    setState(() {
      error = s.t('status.review');
    });
  }

  Future<void> _activate() async {
    await _run(() async {
      final res = await api.activate(appId!);
      activationMsg = res['activation_instructions'] as String?;
      statusText = res['status'] as String?;
      await _refreshPassport();
      setState(() {
        step = StepId.done;
        showPassport = true;
      });
    });
  }

  List<Map<String, dynamic>> get filteredBanks {
    final q = bankQuery.trim().toLowerCase();
    if (q.isEmpty) return banks;
    return banks.where((b) {
      final name = (b['bank_name'] as String? ?? '').toLowerCase();
      final id = (b['bank_id'] as String? ?? '').toLowerCase();
      final code = (b['short_code'] as String? ?? '').toLowerCase();
      return name.contains(q) || id.contains(q) || code.contains(q);
    }).toList();
  }

  int get progressIndex {
    const order = [
      StepId.welcome,
      StepId.bank,
      StepId.consent,
      StepId.fayda,
      StepId.otp,
      StepId.liveness,
      StepId.fields,
      StepId.sign,
      StepId.status,
      StepId.done,
    ];
    return order.indexOf(step).clamp(0, order.length - 1);
  }

  @override
  void dispose() {
    incomeCtrl.dispose();
    occupationCtrl.dispose();
    branchCtrl.dispose();
    sigCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (deviceFp == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 16,
        title: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.asset('assets/icon/app_icon.png', width: 28, height: 28, fit: BoxFit.cover),
            ),
            const SizedBox(width: 10),
            Text(s.t('brand')),
          ],
        ),
        actions: [
          PopupMenuButton<String>(
            tooltip: 'Language',
            initialValue: locale,
            onSelected: (v) async {
              setState(() => locale = v);
              await _persistSession();
            },
            itemBuilder: (_) => [
              const PopupMenuItem(value: 'en', child: Text('English')),
              const PopupMenuItem(value: 'am', child: Text('አማርኛ')),
              const PopupMenuItem(value: 'om', child: Text('Afaan Oromoo')),
            ],
            icon: const Icon(Icons.translate_rounded, size: 22),
          ),
          if (myApps.isNotEmpty)
            IconButton(
              tooltip: 'Passport',
              onPressed: () async {
                await _refreshPassport();
                setState(() => showPassport = true);
              },
              icon: const Icon(Icons.account_balance_wallet_outlined, size: 22),
            ),
          IconButton(
            tooltip: 'API settings',
            onPressed: () => _openSettings(context),
            icon: const Icon(Icons.tune_rounded, size: 22),
          ),
        ],
        bottom: showPassport
            ? null
            : PreferredSize(
                preferredSize: const Size.fromHeight(18),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                  child: _StepRail(index: progressIndex, total: 10),
                ),
              ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (error != null)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: EkycColors.dangerSoft,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: EkycColors.danger.withValues(alpha: 0.25)),
                ),
                child: Text(error!, style: const TextStyle(color: EkycColors.danger, height: 1.35)),
              ),
            Expanded(
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 260),
                switchInCurve: Curves.easeOutCubic,
                switchOutCurve: Curves.easeInCubic,
                child: Padding(
                  key: ValueKey('${showPassport}_$step'),
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
                  child: showPassport ? _buildPassport(context) : _buildStep(context),
                ),
              ),
            ),
            if (busy) const LinearProgressIndicator(minHeight: 2, color: EkycColors.teal),
          ],
        ),
      ),
    );
  }

  Widget _buildPassport(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(s.t('passport.title'), style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 6),
        Text(s.t('passport.subtitle'), style: Theme.of(context).textTheme.bodyMedium),
        const SizedBox(height: 14),
        Expanded(
          child: myApps.isEmpty
              ? Center(child: Text(s.t('passport.empty')))
              : ListView.separated(
                  itemCount: myApps.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, i) {
                    final row = myApps[i];
                    final status = row['status']?.toString() ?? '';
                    final opened = status == 'ACCOUNT_OPENED' || status == 'ACTIVATED';
                    final expired = status == 'EXPIRED';
                    final label = opened
                        ? s.t('passport.opened')
                        : expired
                            ? s.t('passport.expired')
                            : s.t('passport.processing');
                    return Material(
                      color: EkycColors.surface,
                      borderRadius: BorderRadius.circular(14),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(14),
                        onTap: expired || busy ? null : () => _resumeApp(row),
                        child: Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(color: EkycColors.line),
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      row['bank_id']?.toString() ?? '',
                                      style: const TextStyle(fontWeight: FontWeight.w700),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      '$label · ${row['tier']} · $status',
                                      style: const TextStyle(color: EkycColors.muted, fontSize: 12.5),
                                    ),
                                    if (row['account_number'] != null)
                                      Text(
                                        row['account_number'].toString(),
                                        style: const TextStyle(
                                          color: EkycColors.navy,
                                          fontWeight: FontWeight.w700,
                                          fontSize: 16,
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                              if (!expired)
                                Text(s.t('passport.resume'), style: const TextStyle(color: EkycColors.teal)),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
        ),
        FilledButton(
          onPressed: busy
              ? null
              : () {
                  setState(() {
                    showPassport = false;
                    step = StepId.welcome;
                  });
                },
          child: Text(s.t('passport.open_bank')),
        ),
      ],
    );
  }

  Widget _buildStep(BuildContext context) {
    switch (step) {
      case StepId.welcome:
        return _Welcome(onStart: busy ? null : _loadBanksAndStart);
      case StepId.bank:
        return _BankList(
          banks: filteredBanks,
          query: bankQuery,
          onQuery: (v) => setState(() => bankQuery = v),
          onSelect: busy ? null : _selectBank,
        );
      case StepId.consent:
        return _Consent(
          bankName: bankName ?? '',
          onAgree: busy ? null : () => _consent(true),
          onRefuse: busy ? null : () => _consent(false),
        );
      case StepId.fayda:
        return _FaydaFin(
          fin: fin,
          onChanged: (v) => setState(() => fin = v),
          onContinue: busy ? null : _startOtp,
        );
      case StepId.otp:
        return _Otp(
          otp: otp,
          onChanged: (v) => setState(() => otp = v),
          onVerify: busy ? null : _verifyOtp,
        );
      case StepId.liveness:
        return _Liveness(score: livenessScore, onCapture: busy ? null : _captureLiveness);
      case StepId.fields:
        return _Fields(
          bankName: bankName ?? 'Bank',
          incomeCtrl: incomeCtrl,
          occupationCtrl: occupationCtrl,
          branchCtrl: branchCtrl,
          sourceOfFunds: sourceOfFunds,
          onSource: (v) => setState(() => sourceOfFunds = v),
          onContinue: busy ? null : _saveFields,
        );
      case StepId.sign:
        return _Sign(controller: sigCtrl, onSubmit: busy ? null : _submit);
      case StepId.status:
        return _Status(
          status: statusText,
          account: accountNumber,
          bankName: bankName,
          onActivate: (accountNumber != null && !busy) ? _activate : null,
        );
      case StepId.done:
        return _Done(
          status: statusText,
          account: accountNumber,
          bankName: bankName,
          message: activationMsg,
          onRestart: () async {
            await _refreshPassport();
            setState(() {
              showPassport = true;
              step = StepId.welcome;
              appId = null;
              accountNumber = null;
              activationMsg = null;
              error = null;
              bankQuery = '';
              sigCtrl.clear();
            });
          },
        );
    }
  }

  Future<void> _openSettings(BuildContext context) async {
    final ctrl = TextEditingController(text: apiBase);
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: EkycColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return Padding(
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 20,
            bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('API endpoint', style: Theme.of(ctx).textTheme.titleLarge),
              const SizedBox(height: 8),
              const Text(
                'Production: https://ekyc-api-jj0j.onrender.com\n'
                'Local: http://127.0.0.1:8005 (with adb reverse)',
                style: TextStyle(color: EkycColors.muted, height: 1.45),
              ),
              const SizedBox(height: 12),
              TextField(controller: ctrl, decoration: const InputDecoration(labelText: 'Base URL')),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () async {
                  await _saveApiBase(ctrl.text.trim());
                  if (ctx.mounted) Navigator.pop(ctx);
                },
                child: const Text('Save'),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _StepRail extends StatelessWidget {
  const _StepRail({required this.index, required this.total});
  final int index;
  final int total;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(total, (i) {
        final active = i <= index;
        return Expanded(
          child: Container(
            height: 3,
            margin: EdgeInsets.only(right: i == total - 1 ? 0 : 3),
            decoration: BoxDecoration(
              color: active ? EkycColors.teal : EkycColors.line,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        );
      }),
    );
  }
}

class _Welcome extends StatelessWidget {
  const _Welcome({required this.onStart});
  final VoidCallback? onStart;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: Stack(
            children: [
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(20),
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [EkycColors.navyDeep, EkycColors.navy, Color(0xFF123A52)],
                    ),
                  ),
                ),
              ),
              Positioned(
                right: -40,
                top: -30,
                child: Container(
                  width: 180,
                  height: 180,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: EkycColors.tealBright.withValues(alpha: 0.12),
                  ),
                ),
              ),
              Positioned(
                left: -20,
                bottom: 40,
                child: Container(
                  width: 120,
                  height: 120,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: EkycColors.gold.withValues(alpha: 0.10),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(22, 28, 22, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(16),
                      child: Image.asset('assets/icon/app_icon.png', width: 64, height: 64, fit: BoxFit.cover),
                    ),
                    const Spacer(),
                    Text(
                      'Fayda Onboard',
                      style: Theme.of(context).textTheme.displaySmall?.copyWith(
                            color: Colors.white,
                            fontSize: 36,
                          ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Open a commercial bank account with Ethiopia’s national ID — verify once, submit from your phone.',
                      style: TextStyle(color: Color(0xFFC9D4E0), height: 1.5, fontSize: 16),
                    ),
                    const SizedBox(height: 22),
                    const Text(
                      '22 partner banks  ·  VeriFayda OTP  ·  Branch-free',
                      style: TextStyle(color: Color(0xFF8FA3B8), fontSize: 13, height: 1.4),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        FilledButton(onPressed: onStart, child: const Text('Choose your bank')),
        const SizedBox(height: 8),
      ],
    );
  }
}

class _BankList extends StatelessWidget {
  const _BankList({
    required this.banks,
    required this.query,
    required this.onQuery,
    required this.onSelect,
  });
  final List<Map<String, dynamic>> banks;
  final String query;
  final ValueChanged<String> onQuery;
  final void Function(Map<String, dynamic>)? onSelect;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Choose a bank', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 6),
        Text(
          banks.isEmpty ? 'Loading partner banks…' : '${banks.length} Ethiopian commercial banks',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 14),
        TextField(
          onChanged: onQuery,
          decoration: const InputDecoration(
            hintText: 'Search by name or code',
            prefixIcon: Icon(Icons.search, size: 20),
          ),
        ),
        const SizedBox(height: 12),
        Expanded(
          child: banks.isEmpty
              ? const Center(child: CircularProgressIndicator(color: EkycColors.teal))
              : ListView.separated(
                  itemCount: banks.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, i) {
                    final b = banks[i];
                    final name = b['bank_name']?.toString() ?? '';
                    final code = (b['short_code']?.toString().isNotEmpty == true)
                        ? b['short_code'].toString()
                        : (b['bank_id']?.toString() ?? '')
                            .replaceFirst('bank_', '')
                            .toUpperCase();
                    final city = b['hq_city']?.toString() ?? 'Ethiopia';
                    final hue = (name.hashCode.abs() % 40) + 170;
                    return Material(
                      color: EkycColors.surface,
                      borderRadius: BorderRadius.circular(14),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(14),
                        onTap: onSelect == null ? null : () => onSelect!(b),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(color: EkycColors.line),
                          ),
                          child: Row(
                            children: [
                              Container(
                                width: 44,
                                height: 44,
                                alignment: Alignment.center,
                                decoration: BoxDecoration(
                                  color: HSLColor.fromAHSL(1, hue.toDouble(), 0.28, 0.92).toColor(),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: Text(
                                  code.length > 4 ? code.substring(0, 4) : code,
                                  style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    fontSize: 11,
                                    letterSpacing: 0.3,
                                    color: HSLColor.fromAHSL(1, hue.toDouble(), 0.45, 0.32).toColor(),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      name,
                                      style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                        color: EkycColors.ink,
                                        fontSize: 15,
                                      ),
                                    ),
                                    const SizedBox(height: 3),
                                    Text(
                                      '$city · live sandbox',
                                      style: const TextStyle(color: EkycColors.muted, fontSize: 12.5),
                                    ),
                                  ],
                                ),
                              ),
                              const Icon(Icons.arrow_forward_ios_rounded, size: 14, color: EkycColors.muted),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }
}

class _Consent extends StatelessWidget {
  const _Consent({required this.bankName, required this.onAgree, required this.onRefuse});
  final String bankName;
  final VoidCallback? onAgree;
  final VoidCallback? onRefuse;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        Text('Consent', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 16),
        _InfoBlock(
          title: 'National ID check',
          body:
              'We will query the National ID Program via EthSwitch VeriFayda using your 12-digit FIN. Raw FIN values are never stored in plaintext.',
        ),
        const SizedBox(height: 10),
        _InfoBlock(
          title: 'Shared with $bankName',
          body:
              'Verified demographics (name, date of birth, gender) and your application details are sent only to the bank you selected.',
        ),
        const SizedBox(height: 10),
        const _InfoBlock(
          title: 'Biometrics',
          body: 'Selfie frames are processed for liveness, then discarded after hand-off. They are not kept as a permanent gallery.',
        ),
        const SizedBox(height: 28),
        FilledButton(onPressed: onAgree, child: const Text('I agree — continue')),
        const SizedBox(height: 10),
        OutlinedButton(onPressed: onRefuse, child: const Text('Decline')),
      ],
    );
  }
}

class _InfoBlock extends StatelessWidget {
  const _InfoBlock({required this.title, required this.body});
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: EkycColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: EkycColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700, color: EkycColors.ink)),
          const SizedBox(height: 6),
          Text(body, style: const TextStyle(color: EkycColors.muted, height: 1.45)),
        ],
      ),
    );
  }
}

class _FaydaFin extends StatelessWidget {
  const _FaydaFin({required this.fin, required this.onChanged, required this.onContinue});
  final String fin;
  final ValueChanged<String> onChanged;
  final VoidCallback? onContinue;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        Text('Fayda FIN', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        const Text('Enter your 12-digit Fayda Identification Number.'),
        const SizedBox(height: 18),
        TextField(
          keyboardType: TextInputType.number,
          maxLength: 12,
          style: const TextStyle(fontSize: 22, letterSpacing: 2, fontWeight: FontWeight.w600, color: EkycColors.ink),
          decoration: const InputDecoration(labelText: 'FIN', counterText: ''),
          onChanged: onChanged,
        ),
        const SizedBox(height: 18),
        FilledButton(onPressed: onContinue, child: const Text('Send OTP')),
      ],
    );
  }
}

class _Otp extends StatelessWidget {
  const _Otp({required this.otp, required this.onChanged, required this.onVerify});
  final String otp;
  final ValueChanged<String> onChanged;
  final VoidCallback? onVerify;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        Text('SMS verification', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        const Text('Enter the 6-digit code sent for this Fayda challenge.'),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: EkycColors.tealSoft,
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Text(
            'Sandbox OTP: 123456',
            style: TextStyle(color: EkycColors.teal, fontWeight: FontWeight.w600),
          ),
        ),
        const SizedBox(height: 18),
        TextField(
          keyboardType: TextInputType.number,
          maxLength: 6,
          style: const TextStyle(fontSize: 28, letterSpacing: 8, fontWeight: FontWeight.w700, color: EkycColors.ink),
          decoration: const InputDecoration(labelText: 'OTP', counterText: ''),
          onChanged: onChanged,
        ),
        const SizedBox(height: 18),
        FilledButton(onPressed: onVerify, child: const Text('Verify identity')),
      ],
    );
  }
}

class _Liveness extends StatelessWidget {
  const _Liveness({required this.score, required this.onCapture});
  final double? score;
  final VoidCallback? onCapture;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Face check', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        const Text('Center your face and capture a live selfie. Frames are discarded after verification.'),
        const Spacer(),
        Container(
          height: 220,
          decoration: BoxDecoration(
            color: EkycColors.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: EkycColors.line),
          ),
          child: const Center(
            child: Icon(Icons.face_retouching_natural_outlined, size: 72, color: EkycColors.muted),
          ),
        ),
        if (score != null) ...[
          const SizedBox(height: 12),
          Text('Liveness score ${score!.toStringAsFixed(2)}', textAlign: TextAlign.center),
        ],
        const Spacer(),
        FilledButton(onPressed: onCapture, child: const Text('Open camera')),
        const SizedBox(height: 8),
      ],
    );
  }
}

class _Fields extends StatelessWidget {
  const _Fields({
    required this.bankName,
    required this.incomeCtrl,
    required this.occupationCtrl,
    required this.branchCtrl,
    required this.sourceOfFunds,
    required this.onSource,
    required this.onContinue,
  });
  final String bankName;
  final TextEditingController incomeCtrl;
  final TextEditingController occupationCtrl;
  final TextEditingController branchCtrl;
  final String sourceOfFunds;
  final ValueChanged<String> onSource;
  final VoidCallback? onContinue;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        Text('$bankName details', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 16),
        TextField(
          controller: incomeCtrl,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Monthly income (ETB)'),
        ),
        const SizedBox(height: 12),
        TextField(controller: occupationCtrl, decoration: const InputDecoration(labelText: 'Occupation')),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          // ignore: deprecated_member_use
          value: sourceOfFunds,
          items: const [
            DropdownMenuItem(value: 'Salary', child: Text('Salary')),
            DropdownMenuItem(value: 'Business', child: Text('Business')),
            DropdownMenuItem(value: 'Remittance', child: Text('Remittance')),
            DropdownMenuItem(value: 'Savings', child: Text('Savings')),
            DropdownMenuItem(value: 'Agriculture', child: Text('Agriculture')),
          ],
          onChanged: (v) {
            if (v != null) onSource(v);
          },
          decoration: const InputDecoration(labelText: 'Source of funds'),
        ),
        const SizedBox(height: 12),
        TextField(controller: branchCtrl, decoration: const InputDecoration(labelText: 'Branch code (optional)')),
        const SizedBox(height: 20),
        FilledButton(onPressed: onContinue, child: const Text('Continue to signature')),
      ],
    );
  }
}

class _Sign extends StatelessWidget {
  const _Sign({required this.controller, required this.onSubmit});
  final SignatureController controller;
  final VoidCallback? onSubmit;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Sign application', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        const Text('Draw your signature below to authorize submission to the bank.'),
        const SizedBox(height: 14),
        Expanded(
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: EkycColors.line),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Signature(controller: controller, backgroundColor: Colors.white),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(onPressed: controller.clear, child: const Text('Clear')),
            ),
            const SizedBox(width: 12),
            Expanded(
              flex: 2,
              child: FilledButton(onPressed: onSubmit, child: const Text('Submit to bank')),
            ),
          ],
        ),
        const SizedBox(height: 8),
      ],
    );
  }
}

class _Status extends StatelessWidget {
  const _Status({
    required this.status,
    required this.account,
    required this.bankName,
    required this.onActivate,
  });
  final String? status;
  final String? account;
  final String? bankName;
  final VoidCallback? onActivate;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Application status', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 20),
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: EkycColors.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: EkycColors.line),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(bankName ?? 'Bank', style: const TextStyle(color: EkycColors.muted)),
              const SizedBox(height: 8),
              Text(status ?? '…', style: Theme.of(context).textTheme.titleLarge),
              if (account != null) ...[
                const SizedBox(height: 16),
                const Text('Account number', style: TextStyle(color: EkycColors.muted, fontSize: 13)),
                const SizedBox(height: 4),
                Text(
                  account!,
                  style: const TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.5,
                    color: EkycColors.navy,
                  ),
                ),
              ],
            ],
          ),
        ),
        const Spacer(),
        if (onActivate != null)
          FilledButton(onPressed: onActivate, child: const Text('Activate account'))
        else
          const Text('Waiting for bank confirmation…', textAlign: TextAlign.center),
        const SizedBox(height: 8),
      ],
    );
  }
}

class _Done extends StatelessWidget {
  const _Done({
    required this.status,
    required this.account,
    required this.bankName,
    required this.message,
    required this.onRestart,
  });
  final String? status;
  final String? account;
  final String? bankName;
  final String? message;
  final VoidCallback onRestart;

  @override
  Widget build(BuildContext context) {
    final cancelled = status == 'CANCELLED';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Spacer(),
        Icon(
          cancelled ? Icons.cancel_outlined : Icons.check_circle_outline,
          size: 56,
          color: cancelled ? EkycColors.danger : EkycColors.teal,
        ),
        const SizedBox(height: 16),
        Text(
          cancelled ? 'Session ended' : 'Account ready',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 10),
        if (account != null)
          Text('$bankName · $account', style: const TextStyle(color: EkycColors.navy, fontWeight: FontWeight.w600)),
        if (message != null) ...[
          const SizedBox(height: 12),
          Text(message!, style: const TextStyle(height: 1.45)),
        ],
        const Spacer(),
        FilledButton(onPressed: onRestart, child: const Text('Start another application')),
        const SizedBox(height: 8),
      ],
    );
  }
}
