import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:signature/signature.dart';
import 'package:uuid/uuid.dart';

import 'api/ekyc_api.dart';
import 'theme.dart';

/// Default: Render free-tier API. Override with --dart-define=API_BASE=... or in-app Settings.
const kDefaultApiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'https://ekyc-api-jj0j.onrender.com',
);

void main() {
  WidgetsFlutterBinding.ensureInitialized();
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
  final branchCtrl = TextEditingController(text: 'AW-BOLE-01');
  String? accountNumber;
  String? statusText;
  String? activationMsg;

  final sigCtrl = SignatureController(
    penStrokeWidth: 2.4,
    penColor: EkycColors.parchment,
    exportBackgroundColor: EkycColors.forest,
  );

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final prefs = await SharedPreferences.getInstance();
    apiBase = prefs.getString('api_base') ?? kDefaultApiBase;
    var fp = prefs.getString('device_fp');
    if (fp == null || fp.isEmpty) {
      fp = sha256.convert(utf8.encode('dev-${const Uuid().v4()}')).toString().substring(0, 32);
      await prefs.setString('device_fp', fp);
    }
    deviceFp = fp;
    api = EkycApi(baseUrl: apiBase, deviceFingerprint: fp);
    setState(() {});
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
    } on EkycApiException catch (e) {
      setState(() => error = e.message);
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
      if (banks.isEmpty) throw Exception('No partner banks available');
      setState(() => step = StepId.bank);
    });
  }

  Future<void> _selectBank(Map<String, dynamic> bank) async {
    await _run(() async {
      bankId = bank['bank_id'] as String;
      bankName = bank['bank_name'] as String? ?? bankId;
      final created = await api.createApplication(
        userRef: 'usr_${deviceFp!.substring(0, 10)}',
        bankId: bankId!,
      );
      appId = created['application_id'] as String;
      setState(() => step = StepId.consent);
    });
  }

  Future<void> _consent(bool accepted) async {
    await _run(() async {
      final res = await api.consent(appId!, accepted: accepted);
      if (!accepted) {
        setState(() {
          step = StepId.done;
          statusText = res['status'] as String?;
          activationMsg = 'Consent declined. No personal data was sent to Fayda or the bank.';
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
      final b64 = base64Encode(bytes);
      final res = await api.liveness(appId!, b64);
      livenessScore = (res['liveness_score'] as num?)?.toDouble();
      setState(() => step = StepId.fields);
    });
  }

  Future<void> _saveFields() async {
    await _run(() async {
      await api.saveDetails(appId!, {
        'monthly_income_etb': double.parse(incomeCtrl.text.trim()),
        'occupation': occupationCtrl.text.trim(),
        'source_of_funds': sourceOfFunds,
        'branch_code': branchCtrl.text.trim(),
      });
      setState(() => step = StepId.sign);
    });
  }

  Future<void> _submit() async {
    await _run(() async {
      if (sigCtrl.isEmpty) throw Exception('Please sign before submitting');
      final png = await sigCtrl.toPngBytes();
      if (png == null || png.isEmpty) throw Exception('Could not export signature');
      final sigB64 = base64Encode(png);
      await api.submit(appId!, sigB64);
      setState(() => step = StepId.status);
      await _pollStatus();
    });
  }

  Future<void> _pollStatus() async {
    for (var i = 0; i < 40; i++) {
      final data = await api.getApplication(appId!);
      statusText = data['status'] as String?;
      accountNumber = data['account_number'] as String?;
      setState(() {});
      if (statusText == 'ACCOUNT_OPENED' && accountNumber != null) {
        return;
      }
      if (statusText == 'BANK_REJECTED') {
        throw Exception('Bank rejected the application');
      }
      await Future<void>.delayed(const Duration(milliseconds: 700));
    }
    throw Exception('Timed out waiting for bank account issuance');
  }

  Future<void> _activate() async {
    await _run(() async {
      final res = await api.activate(appId!);
      activationMsg = res['activation_instructions'] as String?;
      statusText = res['status'] as String?;
      setState(() => step = StepId.done);
    });
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
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF071E18), EkycColors.forest, Color(0xFF163C2E)],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              _Header(
                apiBase: apiBase,
                onSettings: () => _openSettings(context),
              ),
              if (error != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                  child: Material(
                    color: EkycColors.danger.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(12),
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Text(error!, style: const TextStyle(color: Color(0xFFFFC9C9))),
                    ),
                  ),
                ),
              Expanded(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 280),
                  child: Padding(
                    key: ValueKey(step),
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: _buildStep(context),
                  ),
                ),
              ),
              if (busy)
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: LinearProgressIndicator(color: EkycColors.brass),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStep(BuildContext context) {
    switch (step) {
      case StepId.welcome:
        return _Welcome(onStart: busy ? null : _loadBanksAndStart);
      case StepId.bank:
        return _BankList(banks: banks, onSelect: busy ? null : _selectBank);
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
          hint: 'Sandbox OTP for pilot: 123456',
        );
      case StepId.liveness:
        return _Liveness(
          score: livenessScore,
          onCapture: busy ? null : _captureLiveness,
        );
      case StepId.fields:
        return _Fields(
          incomeCtrl: incomeCtrl,
          occupationCtrl: occupationCtrl,
          branchCtrl: branchCtrl,
          sourceOfFunds: sourceOfFunds,
          onSource: (v) => setState(() => sourceOfFunds = v),
          onContinue: busy ? null : _saveFields,
        );
      case StepId.sign:
        return _Sign(
          controller: sigCtrl,
          onSubmit: busy ? null : _submit,
        );
      case StepId.status:
        return _Status(
          status: statusText,
          account: accountNumber,
          onActivate: (accountNumber != null && !busy) ? _activate : null,
        );
      case StepId.done:
        return _Done(
          status: statusText,
          account: accountNumber,
          message: activationMsg,
          onRestart: () => setState(() {
            step = StepId.welcome;
            appId = null;
            accountNumber = null;
            activationMsg = null;
            error = null;
            sigCtrl.clear();
          }),
        );
    }
  }

  Future<void> _openSettings(BuildContext context) async {
    final ctrl = TextEditingController(text: apiBase);
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: EkycColors.canopy,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
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
                'USB cable: run adb reverse tcp:8005 tcp:8005 and keep http://127.0.0.1:8005\n'
                'Same Wi‑Fi: use http://<your-pc-lan-ip>:8005',
                style: TextStyle(color: EkycColors.mist, height: 1.4),
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

class _Header extends StatelessWidget {
  const _Header({required this.apiBase, required this.onSettings});
  final String apiBase;
  final VoidCallback onSettings;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 8, 8),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: EkycColors.brass, width: 1.5),
              gradient: const RadialGradient(
                colors: [Color(0xFF3D6B54), EkycColors.forest],
              ),
            ),
            child: const Icon(Icons.verified_user, color: EkycColors.brass, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Fayda Onboard', style: Theme.of(context).textTheme.titleLarge),
                Text(
                  apiBase.replaceFirst('http://', ''),
                  style: const TextStyle(color: EkycColors.mist, fontSize: 12),
                ),
              ],
            ),
          ),
          IconButton(onPressed: onSettings, icon: const Icon(Icons.settings_outlined)),
        ],
      ),
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
        const Spacer(),
        Text('Open a bank account\nwith your Fayda ID', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 14),
        const Text(
          'Consent, national ID verification, liveness check, and digital submission — without visiting a branch.',
          style: TextStyle(color: EkycColors.mist, height: 1.45),
        ),
        const Spacer(),
        ElevatedButton(onPressed: onStart, child: const Text('Begin onboarding')),
        const SizedBox(height: 24),
      ],
    );
  }
}

class _BankList extends StatelessWidget {
  const _BankList({required this.banks, required this.onSelect});
  final List<Map<String, dynamic>> banks;
  final void Function(Map<String, dynamic>)? onSelect;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        Text('Choose your bank', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 16),
        ...banks.map((b) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: InkWell(
              onTap: onSelect == null ? null : () => onSelect!(b),
              borderRadius: BorderRadius.circular(16),
              child: Ink(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: EkycColors.brass.withValues(alpha: 0.4)),
                  color: EkycColors.canopy.withValues(alpha: 0.7),
                ),
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(b['bank_name']?.toString() ?? '', style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 4),
                    Text(
                      'Tiers: ${(b['supported_tiers'] as List?)?.join(', ') ?? ''}',
                      style: const TextStyle(color: EkycColors.mist),
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
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
        const SizedBox(height: 12),
        Text(
          'We will query the National ID Program via EthSwitch VeriFayda using your 12-digit FIN. '
          'Verified demographics will be sent to $bankName. Biometric frames are discarded after hand-off. '
          'Raw Fayda numbers are never stored in plaintext.',
          style: const TextStyle(height: 1.5),
        ),
        const SizedBox(height: 28),
        ElevatedButton(onPressed: onAgree, child: const Text('Agree & continue')),
        const SizedBox(height: 10),
        OutlinedButton(onPressed: onRefuse, child: const Text('Decline & exit')),
      ],
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
        Text('Fayda national ID', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 16),
        TextField(
          keyboardType: TextInputType.number,
          maxLength: 12,
          decoration: const InputDecoration(labelText: '12-digit FIN', counterText: ''),
          onChanged: onChanged,
        ),
        const SizedBox(height: 16),
        ElevatedButton(onPressed: onContinue, child: const Text('Send OTP')),
      ],
    );
  }
}

class _Otp extends StatelessWidget {
  const _Otp({required this.otp, required this.onChanged, required this.onVerify, required this.hint});
  final String otp;
  final ValueChanged<String> onChanged;
  final VoidCallback? onVerify;
  final String hint;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        Text('Enter SMS OTP', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        Text(hint, style: const TextStyle(color: EkycColors.brass)),
        const SizedBox(height: 16),
        TextField(
          keyboardType: TextInputType.number,
          maxLength: 6,
          decoration: const InputDecoration(labelText: '6-digit code', counterText: ''),
          onChanged: onChanged,
        ),
        const SizedBox(height: 16),
        ElevatedButton(onPressed: onVerify, child: const Text('Verify identity')),
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
        Text('Face liveness', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 12),
        const Text('Center your face and capture a live selfie. Frames are processed then discarded.'),
        const Spacer(),
        if (score != null)
          Text('Previous score: ${score!.toStringAsFixed(2)}', textAlign: TextAlign.center),
        ElevatedButton(onPressed: onCapture, child: const Text('Open camera & capture')),
        const SizedBox(height: 24),
      ],
    );
  }
}

class _Fields extends StatelessWidget {
  const _Fields({
    required this.incomeCtrl,
    required this.occupationCtrl,
    required this.branchCtrl,
    required this.sourceOfFunds,
    required this.onSource,
    required this.onContinue,
  });
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
        Text('Bank details', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 16),
        TextField(controller: incomeCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Monthly income (ETB)')),
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
          ],
          onChanged: (v) {
            if (v != null) onSource(v);
          },
          decoration: const InputDecoration(labelText: 'Source of funds'),
        ),
        const SizedBox(height: 12),
        TextField(controller: branchCtrl, decoration: const InputDecoration(labelText: 'Branch code')),
        const SizedBox(height: 20),
        ElevatedButton(onPressed: onContinue, child: const Text('Continue to signature')),
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
        Text('Digital signature', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 12),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: Container(
              decoration: BoxDecoration(
                border: Border.all(color: EkycColors.brass.withValues(alpha: 0.5)),
                color: EkycColors.canopy,
              ),
              child: Signature(controller: controller, backgroundColor: EkycColors.canopy),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: controller.clear,
                child: const Text('Clear'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              flex: 2,
              child: ElevatedButton(onPressed: onSubmit, child: const Text('Submit to bank')),
            ),
          ],
        ),
        const SizedBox(height: 16),
      ],
    );
  }
}

class _Status extends StatelessWidget {
  const _Status({required this.status, required this.account, required this.onActivate});
  final String? status;
  final String? account;
  final VoidCallback? onActivate;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Application status', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 20),
        Text('Status: ${status ?? '…'}', style: Theme.of(context).textTheme.titleLarge),
        if (account != null) ...[
          const SizedBox(height: 12),
          Text('Account: $account', style: const TextStyle(color: EkycColors.brass, fontSize: 22)),
        ],
        const Spacer(),
        if (onActivate != null)
          ElevatedButton(onPressed: onActivate, child: const Text('Activate account')),
        if (onActivate == null)
          const Text('Waiting for bank CBS…', textAlign: TextAlign.center),
        const SizedBox(height: 24),
      ],
    );
  }
}

class _Done extends StatelessWidget {
  const _Done({
    required this.status,
    required this.account,
    required this.message,
    required this.onRestart,
  });
  final String? status;
  final String? account;
  final String? message;
  final VoidCallback onRestart;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Spacer(),
        Text(status == 'CANCELLED' ? 'Session ended' : 'You are set', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 12),
        if (account != null) Text('Account $account', style: const TextStyle(color: EkycColors.brass, fontSize: 20)),
        if (message != null) ...[
          const SizedBox(height: 12),
          Text(message!, style: const TextStyle(height: 1.45)),
        ],
        const Spacer(),
        ElevatedButton(onPressed: onRestart, child: const Text('Start another application')),
        const SizedBox(height: 24),
      ],
    );
  }
}
