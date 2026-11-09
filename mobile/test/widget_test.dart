import 'package:flutter_test/flutter_test.dart';

import 'package:ekyc_mobile/main.dart';

void main() {
  testWidgets('EkycApp loads onboarding shell', (WidgetTester tester) async {
    await tester.pumpWidget(const EkycApp());
    await tester.pump();
    expect(find.byType(EkycApp), findsOneWidget);
  });
}
