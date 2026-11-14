import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ekyc_mobile/l10n/strings.dart';
import 'package:ekyc_mobile/screens/home_tab.dart';
import 'package:ekyc_mobile/theme.dart';

void main() {
  testWidgets('HomeTab hero fills viewport and landing sections scroll', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      MaterialApp(
        theme: buildEkycTheme(),
        home: Scaffold(
          appBar: AppBar(title: const Text('Fayda')),
          body: HomeTab(
            locale: 'en',
            partnerCount: 22,
            onOpenBank: () {},
          ),
          bottomNavigationBar: NavigationBar(
            destinations: const [
              NavigationDestination(icon: Icon(Icons.home), label: 'Home'),
              NavigationDestination(icon: Icon(Icons.wallet), label: 'Passport'),
              NavigationDestination(icon: Icon(Icons.settings), label: 'Settings'),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Fayda Onboard'), findsWidgets);
    expect(find.text('Open a bank'), findsWidgets);
    expect(find.text('Scroll for the full story'), findsOneWidget);

    // Landing content is below the fold — scroll to reveal each section.
    final scrollable = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(find.text('How it works'), 300, scrollable: scrollable);
    expect(find.text('How it works'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('The platform'), 300, scrollable: scrollable);
    expect(find.text('The platform'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Built for trust'), 300, scrollable: scrollable);
    expect(find.text('Built for trust'), findsOneWidget);
  });

  test('am locale falls back to EN for new home keys', () {
    final am = S('am');
    expect(am.t('home.how_title'), 'How it works');
    expect(am.t('lock.keep_pin_hint'), contains('current PIN'));
  });
}
