import 'dart:convert';

import 'package:http/http.dart' as http;

class EkycApiException implements Exception {
  EkycApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;

  @override
  String toString() => 'EkycApiException($statusCode): $message';
}

class EkycApi {
  EkycApi({required this.baseUrl, required this.deviceFingerprint});

  String baseUrl;
  final String deviceFingerprint;
  String? token;

  Map<String, String> get _headers {
    final h = <String, String>{
      'Content-Type': 'application/json',
      'X-Device-Fingerprint': deviceFingerprint,
    };
    if (token != null && token!.isNotEmpty) {
      h['Authorization'] = 'Bearer $token';
    }
    return h;
  }

  Uri _u(String path) => Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path');

  Future<Map<String, dynamic>> _decode(http.Response r) async {
    final body = r.body.isEmpty ? <String, dynamic>{} : jsonDecode(r.body);
    if (r.statusCode >= 400) {
      final detail = body is Map ? (body['detail'] ?? body).toString() : r.body;
      throw EkycApiException(r.statusCode, detail.toString());
    }
    if (body is Map<String, dynamic>) return body;
    return {'data': body};
  }

  Future<List<dynamic>> listBanks({String? tier}) async {
    final q = (tier == null || tier.isEmpty) ? '' : '?tier=${Uri.encodeQueryComponent(tier)}';
    final r = await http.get(_u('/v1/banks$q'), headers: _headers);
    if (r.statusCode >= 400) {
      throw EkycApiException(r.statusCode, r.body);
    }
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> openDeviceSession(
    String userRef, {
    String? faydaRefHash,
  }) async {
    final body = <String, dynamic>{'user_ref': userRef};
    if (faydaRefHash != null && faydaRefHash.isNotEmpty) {
      body['fayda_ref_hash'] = faydaRefHash;
    }
    final r = await http.post(
      _u('/v1/auth/device'),
      headers: _headers,
      body: jsonEncode(body),
    );
    final data = await _decode(r);
    token = data['token'] as String?;
    return data;
  }

  Future<List<Map<String, dynamic>>> listApplications() async {
    final r = await http.get(_u('/v1/applications'), headers: _headers);
    if (r.statusCode >= 400) {
      throw EkycApiException(r.statusCode, r.body);
    }
    final raw = jsonDecode(r.body);
    if (raw is! List) return [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<Map<String, dynamic>> createApplication({
    required String userRef,
    required String bankId,
    String tier = 'standard',
  }) async {
    final r = await http.post(
      _u('/v1/applications'),
      headers: _headers,
      body: jsonEncode({'user_ref': userRef, 'bank_id': bankId, 'tier': tier}),
    );
    final data = await _decode(r);
    token = data['token'] as String?;
    return data;
  }

  Future<void> refreshToken() async {
    final r = await http.post(_u('/v1/auth/refresh'), headers: _headers);
    final data = await _decode(r);
    token = data['token'] as String?;
  }

  Future<Map<String, dynamic>> consent(String appId, {required bool accepted}) async {
    final r = await http.post(
      _u('/v1/applications/$appId/consent'),
      headers: _headers,
      body: jsonEncode({
        'consent_version': 'v1.0',
        'accepted': accepted,
        'device_fingerprint': deviceFingerprint,
      }),
    );
    return _decode(r);
  }

  Future<Map<String, dynamic>> startIdentity(String appId, String fin) async {
    final r = await http.post(
      _u('/v1/applications/$appId/identity/start'),
      headers: _headers,
      body: jsonEncode({'fin': fin}),
    );
    return _decode(r);
  }

  Future<Map<String, dynamic>> verifyOtp(String appId, String txId, String otp) async {
    final r = await http.post(
      _u('/v1/applications/$appId/identity/verify'),
      headers: _headers,
      body: jsonEncode({'transaction_id': txId, 'otp': otp}),
    );
    return _decode(r);
  }

  Future<Map<String, dynamic>> startPassportIdentity(String fin) async {
    final r = await http.post(
      _u('/v1/passport/identity/start'),
      headers: _headers,
      body: jsonEncode({'fin': fin}),
    );
    return _decode(r);
  }

  Future<Map<String, dynamic>> verifyPassportIdentity(String txId, String otpCode) async {
    final r = await http.post(
      _u('/v1/passport/identity/verify'),
      headers: _headers,
      body: jsonEncode({'transaction_id': txId, 'otp': otpCode}),
    );
    final data = await _decode(r);
    token = data['token'] as String?;
    return data;
  }

  Future<Map<String, dynamic>> bindPassport(String appId) async {
    final r = await http.post(
      _u('/v1/applications/$appId/identity/bind-passport'),
      headers: _headers,
    );
    return _decode(r);
  }

  Future<Map<String, dynamic>> liveness(String appId, String selfieBase64) async {
    final r = await http.post(
      _u('/v1/applications/$appId/liveness'),
      headers: _headers,
      body: jsonEncode({'selfie_base64': selfieBase64}),
    );
    return _decode(r);
  }

  Future<Map<String, dynamic>> saveDetails(
    String appId,
    Map<String, dynamic> fields,
  ) async {
    final r = await http.put(
      _u('/v1/applications/$appId/details'),
      headers: _headers,
      body: jsonEncode({'dynamic_fields': fields}),
    );
    return _decode(r);
  }

  Future<Map<String, dynamic>> submit(String appId, String signature) async {
    final r = await http.post(
      _u('/v1/applications/$appId/submit'),
      headers: _headers,
      body: jsonEncode({'signature': signature}),
    );
    return _decode(r);
  }

  Future<Map<String, dynamic>> getApplication(String appId) async {
    final r = await http.get(_u('/v1/applications/$appId'), headers: _headers);
    return _decode(r);
  }

  Future<Map<String, dynamic>> activate(String appId) async {
    final r = await http.post(_u('/v1/applications/$appId/activate'), headers: _headers);
    return _decode(r);
  }
}
