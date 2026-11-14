import 'package:flutter/material.dart';

import '../l10n/strings.dart';
import '../theme.dart';

/// Post-login Home: full-viewport brand hero (like welcome), then a long
/// scrollable landing page about the product and platform.
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
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final ink = isDark ? const Color(0xFFE8EEF4) : EkycColors.ink;
    final muted = isDark ? const Color(0xFF9AABBC) : EkycColors.muted;
    final divider = isDark ? const Color(0xFF2A3A4C) : EkycColors.line;

    return CustomScrollView(
      physics: const BouncingScrollPhysics(parent: AlwaysScrollableScrollPhysics()),
      slivers: [
        // Fill the visible shell viewport (AppBar + nav already excluded by parent).
        SliverLayoutBuilder(
          builder: (context, constraints) {
            final viewport = constraints.viewportMainAxisExtent;
            // Short peek of the next section so scroll is obvious (~welcome fill).
            final heroH = (viewport - 36).clamp(400.0, 920.0);
            return SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: SizedBox(
                  height: heroH,
                  child: _HomeHero(
                    brand: s.t('brand'),
                    howto: s.t('home.howto'),
                    countLabel: countLabel,
                    cta: s.t('home.cta'),
                    scrollHint: s.t('home.scroll_hint'),
                    busy: busy,
                    onOpenBank: onOpenBank,
                  ),
                ),
              ),
            );
          },
        ),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(24, 36, 24, 12),
          sliver: SliverList(
            delegate: SliverChildListDelegate([
              Text(
                s.t('home.how_title'),
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(color: ink),
              ),
              const SizedBox(height: 18),
              _HowStep(
                index: '01',
                title: s.t('home.how_1_title'),
                body: s.t('home.how_1_body'),
                titleColor: ink,
                bodyColor: muted,
                dividerColor: divider,
              ),
              _HowStep(
                index: '02',
                title: s.t('home.how_2_title'),
                body: s.t('home.how_2_body'),
                titleColor: ink,
                bodyColor: muted,
                dividerColor: divider,
              ),
              _HowStep(
                index: '03',
                title: s.t('home.how_3_title'),
                body: s.t('home.how_3_body'),
                titleColor: ink,
                bodyColor: muted,
                dividerColor: divider,
                showDivider: false,
              ),
              const SizedBox(height: 36),
              Text(
                s.t('home.platform_title'),
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(color: ink),
              ),
              const SizedBox(height: 10),
              Text(
                s.t('home.platform_body'),
                style: TextStyle(color: muted, height: 1.55, fontSize: 15),
              ),
              const SizedBox(height: 14),
              Text(
                countLabel,
                style: TextStyle(
                  color: isDark ? EkycColors.tealBright : EkycColors.teal,
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                  letterSpacing: 0.2,
                ),
              ),
              const SizedBox(height: 36),
              Text(
                s.t('home.trust_title'),
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(color: ink),
              ),
              const SizedBox(height: 14),
              _TrustLine(text: s.t('home.trust_1'), color: muted),
              _TrustLine(text: s.t('home.trust_2'), color: muted),
              _TrustLine(text: s.t('home.trust_3'), color: muted),
              const SizedBox(height: 32),
              FilledButton(
                onPressed: busy ? null : onOpenBank,
                child: Text(s.t('home.cta')),
              ),
              const SizedBox(height: 14),
              Text(
                s.t('home.footer'),
                textAlign: TextAlign.center,
                style: TextStyle(color: muted, fontSize: 13, height: 1.4),
              ),
              const SizedBox(height: 28),
            ]),
          ),
        ),
      ],
    );
  }
}

class _HomeHero extends StatelessWidget {
  const _HomeHero({
    required this.brand,
    required this.howto,
    required this.countLabel,
    required this.cta,
    required this.scrollHint,
    required this.busy,
    required this.onOpenBank,
  });

  final String brand;
  final String howto;
  final String countLabel;
  final String cta;
  final String scrollHint;
  final bool busy;
  final VoidCallback? onOpenBank;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [EkycColors.navyDeep, EkycColors.navy, Color(0xFF123A52)],
            ),
          ),
        ),
        Positioned(
          right: -48,
          top: -36,
          child: Container(
            width: 220,
            height: 220,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: EkycColors.tealBright.withValues(alpha: 0.14),
            ),
          ),
        ),
        Positioned(
          left: -28,
          bottom: 72,
          child: Container(
            width: 140,
            height: 140,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: EkycColors.gold.withValues(alpha: 0.12),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 22),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Image.asset(
                  'assets/icon/app_icon.png',
                  width: 64,
                  height: 64,
                  fit: BoxFit.cover,
                ),
              ),
              const Spacer(flex: 3),
              Text(
                brand,
                style: Theme.of(context).textTheme.displaySmall?.copyWith(
                      color: Colors.white,
                      fontSize: 38,
                      height: 1.05,
                    ),
              ),
              const SizedBox(height: 14),
              Text(
                howto,
                style: const TextStyle(color: Color(0xFFC9D4E0), height: 1.5, fontSize: 16),
              ),
              const SizedBox(height: 18),
              Text(
                countLabel,
                style: const TextStyle(color: Color(0xFF8FA3B8), fontSize: 13, height: 1.4),
              ),
              const Spacer(flex: 2),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: EkycColors.teal,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  onPressed: busy ? null : onOpenBank,
                  child: Text(cta),
                ),
              ),
              const SizedBox(height: 14),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.keyboard_arrow_down_rounded,
                    color: Colors.white.withValues(alpha: 0.55),
                    size: 20,
                  ),
                  const SizedBox(width: 4),
                  Flexible(
                    child: Text(
                      scrollHint,
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.55),
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _HowStep extends StatelessWidget {
  const _HowStep({
    required this.index,
    required this.title,
    required this.body,
    required this.titleColor,
    required this.bodyColor,
    required this.dividerColor,
    this.showDivider = true,
  });

  final String index;
  final String title;
  final String body;
  final Color titleColor;
  final Color bodyColor;
  final Color dividerColor;
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Text(
              index,
              style: const TextStyle(
                color: EkycColors.teal,
                fontWeight: FontWeight.w800,
                fontSize: 13,
                letterSpacing: 0.6,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                title,
                style: TextStyle(color: titleColor, fontWeight: FontWeight.w700, fontSize: 17),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.only(left: 36),
          child: Text(body, style: TextStyle(color: bodyColor, height: 1.5, fontSize: 14.5)),
        ),
        if (showDivider) ...[
          const SizedBox(height: 16),
          Divider(height: 1, color: dividerColor),
          const SizedBox(height: 16),
        ],
      ],
    );
  }
}

class _TrustLine extends StatelessWidget {
  const _TrustLine({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 3),
            child: Icon(Icons.check_circle_outline_rounded, size: 18, color: EkycColors.teal),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: TextStyle(color: color, height: 1.45, fontSize: 14.5))),
        ],
      ),
    );
  }
}
