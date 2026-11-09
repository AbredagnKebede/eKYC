import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _securePinKey = 'app_pin_hash';
const _prefsPinKey = 'app_pin_hash';

/// Stores PIN hash in secure storage, with SharedPreferences fallback.
class PinRepository {
  PinRepository({FlutterSecureStorage? secure, this._prefs})
      : _secure = secure ?? const FlutterSecureStorage();

  final FlutterSecureStorage _secure;
  SharedPreferences? _prefs;

  Future<SharedPreferences> _ensurePrefs() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  Future<String?> loadPinHash() async {
    try {
      final fromSecure = await _secure.read(key: _securePinKey);
      if (fromSecure != null && fromSecure.isNotEmpty) {
        return fromSecure;
      }
    } catch (_) {
      // secure storage unavailable on some emulators
    }
    final prefs = await _ensurePrefs();
    return prefs.getString(_prefsPinKey);
  }

  Future<void> savePinHash(String hash) async {
    var savedSecure = false;
    try {
      await _secure.write(key: _securePinKey, value: hash);
      savedSecure = true;
    } catch (_) {}
    final prefs = await _ensurePrefs();
    if (savedSecure) {
      await prefs.remove(_prefsPinKey);
    } else {
      await prefs.setString(_prefsPinKey, hash);
    }
  }

  Future<void> clearPinHash() async {
    try {
      await _secure.delete(key: _securePinKey);
    } catch (_) {}
    final prefs = await _ensurePrefs();
    await prefs.remove(_prefsPinKey);
  }
}
