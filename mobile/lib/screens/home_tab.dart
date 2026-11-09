import 'package:flutter/material.dart';

import '../l10n/strings.dart';
import '../theme.dart';

class HomeTab extends StatelessWidget {
  const HomeTab({
    super.key,
    required this.locale,
    required this.partnerCount,
    required this.onOpenBank,
    this.busy = false,
  });

  final String locale;
  final int? partnerCount;
  final VoidCallback? onOpenBank;
  final bool busy;

  S get s => S(locale);

  @override
  Widget build(BuildContext context) {
    final countLabel = partnerCount == null
        ? '…'
        : partnerCount == 1
            ? s.t('home.banks_one')
            : s.t('home.banks_many').replaceAll('{n}', '$partnerCount');

    return ListView(
      children: [
        Stack(
          children: [
            Container(
              height: 240,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(20),
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [EkycColors.navyDeep, EkycColors.navy, Color(0xFF123A52)],
                ),
              ),
            ),
            Positioned(
              right: -36,
              top: -28,
              child: Container(
                width: 160,
                height: 160,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: EkycColors.tealBright.withValues(alpha: 0.14),
                ),
              ),
            ),
            Positioned(
              left: -18,
              bottom: 32,
              child: Container(
                width: 100,
                height: 100,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: EkycColors.gold.withValues(alpha: 0.12),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(22, 26, 22, 22),
              child: SizedBox(
                height: 240,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(14),
                      child: Image.asset(
                        'assets/icon/app_icon.png',
                        width: 52,
                        height: 52,
                        fit: BoxFit.cover,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      s.t('brand'),
                      style: Theme.of(context).textTheme.displaySmall?.copyWith(
                            color: Colors.white,
                            fontSize: 32,
                          ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      s.t('home.howto'),
                      style: const TextStyle(color: Color(0xFFC9D4E0), height: 1.45, fontSize: 15),
                    ),
                    const SizedBox(height: 14),
                    Text(
                      countLabel,
                      style: const TextStyle(color: Color(0xFF8FA3B8), fontSize: 13, height: 1.4),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 22),
        FilledButton(
          onPressed: busy ? null : onOpenBank,
          child: Text(s.t('home.cta')),
        ),
        const SizedBox(height: 12),
        Text(
          s.t('home.footer'),
          textAlign: TextAlign.center,
          style: const TextStyle(color: EkycColors.muted, fontSize: 13, height: 1.4),
        ),
      ],
    );
  }
}
