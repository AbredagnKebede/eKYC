"""Multilingual Localization Engine (i18n) for Ethiopian Banking Onboarding.

Supports:
- English (en)
- Amharic (am) - አማርኛ
- Afaan Oromo (om) - Afaan Oromoo
- Tigrinya (ti) - ትግርኛ
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, Any


class Locale(str, Enum):
    EN = "en"
    AM = "am"
    OM = "om"
    TI = "ti"


SUPPORTED_LOCALES = [Locale.EN, Locale.AM, Locale.OM, Locale.TI]

LOCALE_NAMES: Dict[Locale, str] = {
    Locale.EN: "English",
    Locale.AM: "አማርኛ",
    Locale.OM: "Afaan Oromoo",
    Locale.TI: "ትግርኛ",
}

TRANSLATIONS: Dict[Locale, Dict[str, str]] = {
    Locale.EN: {
        "app.title": "Ethiopian eKYC Digital Bank Onboarding",
        "app.subtitle": "Open your sovereign bank account with verified Fayda ID",
        "step.select_bank": "Select Bank",
        "step.consent": "Plain Language Consent",
        "step.fayda_input": "Fayda Verification",
        "step.liveness": "Live Selfie Check",
        "step.dynamic_fields": "Account Details",
        "step.signature": "Digital Signature",
        "step.confirmation": "Account Issued",
        "consent.title": "Consent to Identity Verification & Data Sharing",
        "consent.disclosure_fayda": "We query the National ID Program (NIDP) via EthSwitch VeriFayda to confirm your legal identity using your 12-digit FIN. Your biometric vectors and raw credentials are never permanently stored.",
        "consent.disclosure_bank": "Your verified demographic details (full name, date of birth, gender, and photograph) along with dynamic application data will be securely transmitted to your chosen commercial bank.",
        "consent.device_binding": "Client device fingerprint and session metadata are cryptographically logged for fraud prevention.",
        "consent.btn_agree": "Agree & Continue",
        "consent.btn_refuse": "Decline & Exit",
        "consent.refusal_notice": "Consent was declined. You cannot proceed with digital onboarding without consent.",
        "fayda.fin_label": "Fayda National ID Number (FIN)",
        "fayda.fin_placeholder": "1234 5678 9012",
        "fayda.fin_helper": "Enter your 12-digit National Identification Number",
        "fayda.btn_send_otp": "Send Verification OTP",
        "fayda.otp_label": "Enter 6-digit SMS OTP",
        "fayda.otp_placeholder": "123456",
        "fayda.otp_timer": "Resend code in {seconds}s",
        "fayda.btn_verify_otp": "Verify Identity",
        "fayda.err_invalid_fin": "FIN must be exactly 12 numeric digits.",
        "fayda.err_invalid_otp": "OTP must be 6 numeric digits.",
        "fayda.err_lockout": "Too many failed attempts. Identity verification is temporarily locked.",
        "liveness.title": "Facial Liveness & Identity Verification",
        "liveness.instruction_center": "Center your face inside the oval frame",
        "liveness.instruction_blink": "Please blink your eyes naturally",
        "liveness.instruction_turn": "Turn your face slightly to the left",
        "liveness.instruction_smile": "Smile gently towards the camera",
        "liveness.btn_capture": "Capture Selfie",
        "liveness.btn_retake": "Retake Photo",
        "liveness.btn_confirm": "Confirm & Proceed",
        "liveness.success": "Liveness check passed successfully (Score: {score})",
        "liveness.disclaimer": "Selfie frames are held in ephemeral memory and discarded immediately after bank confirmation.",
        "fields.title": "Bank-Specific Information",
        "fields.btn_continue": "Continue to Signature",
        "fields.err_required": "This field is required.",
        "signature.title": "Sign Your Application",
        "signature.instruction": "Draw your digital signature inside the designated box",
        "signature.btn_clear": "Clear Signature",
        "signature.btn_submit": "Submit to Bank Core Banking System",
        "signature.err_empty": "Please provide a valid signature before submitting.",
        "status.processing": "Submitting application to Core Banking System...",
        "status.success": "Congratulations! Your account has been opened.",
        "status.account_number": "Account Number: {account_number}",
        "status.bank_reference": "CBS Reference: {reference}",
    },
    Locale.AM: {
        "app.title": "የኢትዮጵያ ዲጂታል የባንክ አካውንት መክፈቻ",
        "app.subtitle": "በፋይዳ ዲጂታል መታወቂያዎ አማካኝነት በደቂቃዎች ውስጥ አካውንት ይክፈቱ",
        "step.select_bank": "ባንክ ይምረጡ",
        "step.consent": "የስምምነት ማረጋገጫ",
        "step.fayda_input": "የፋይዳ ማረጋገጫ",
        "step.liveness": "የፊት ገጽታ ማረጋገጫ",
        "step.dynamic_fields": "የአካውንት መረጃ",
        "step.signature": "ዲጂታል ፊርማ",
        "step.confirmation": "አካውንቱ ተከፍቷል",
        "consent.title": "የግል መረጃ ማረጋገጫ እና ማጋሪያ ስምምነት",
        "consent.disclosure_fayda": "የእርስዎን ህጋዊ ማንነት ለማረጋገጥ በኢትስዊች ቬሪፋይዳ በኩል ከብሔራዊ መታወቂያ ፕሮግራም ጋር እንገናኛለን። የባዮሜትሪክ መረጃዎ በቋሚነት አይቀመጥም።",
        "consent.disclosure_bank": "የተረጋገጠው ስምዎ፣ የልደት ቀንዎ፣ ጾታዎ እና ፎቶዎ ለመረጡት ባንክ በደህንነት ይተላለፋል።",
        "consent.device_binding": "ለደህንነት ሲባል የመሳሪያዎ መለያ መረጃ ይመዘገባል።",
        "consent.btn_agree": "ተስማምቻለሁ፤ ይቀጥሉ",
        "consent.btn_refuse": "አልስማማም፤ ውጣ",
        "consent.refusal_notice": "ስምምነት አልተደረገም። ያለስምምነት አካውንት መክፈት አይቻልም።",
        "fayda.fin_label": "የፋይዳ ብሔራዊ መታወቂያ ቁጥር (FIN)",
        "fayda.fin_placeholder": "1234 5678 9012",
        "fayda.fin_helper": "ባለ 12 አሃዝ የፋይዳ ቁጥርዎን ያስገቡ",
        "fayda.btn_send_otp": "የማረጋገጫ ኮድ ላክ",
        "fayda.otp_label": "በSMS የተላከውን ባለ 6 አሃዝ ኮድ ያስገቡ",
        "fayda.otp_placeholder": "123456",
        "fayda.otp_timer": "ኮዱን በ{seconds} ሰከንድ ውስጥ እንደገና ይላኩ",
        "fayda.btn_verify_otp": "ማንነትን አረጋግጥ",
        "fayda.err_invalid_fin": "የፋይዳ ቁጥር በትክክል 12 የቁጥር አሃዞች መሆን አለበት።",
        "fayda.err_invalid_otp": "የማረጋገጫ ኮድ ባለ 6 አሃዝ መሆን አለበት።",
        "fayda.err_lockout": "ተደጋጋሚ የተሳሳተ ሙከራ ተደርጓል። እባክዎ ትንሽ ቆይተው ይሞክሩ።",
        "liveness.title": "የፊት ገጽታ የቀጥታ ማረጋገጫ",
        "liveness.instruction_center": "ፊትዎን በክቡ ማዕቀፍ ውስጥ ያስተካክሉ",
        "liveness.instruction_blink": "እባክዎን ዓይንዎን ያርገብግቡ",
        "liveness.instruction_turn": "ፊትዎን በትንሹ ወደ ግራ ያዙሩ",
        "liveness.instruction_smile": "ፈገግ ይበሉ",
        "liveness.btn_capture": "ፎቶ አንሳ",
        "liveness.btn_retake": "እንደገና አንሳ",
        "liveness.btn_confirm": "አረጋግጥና ቀጥል",
        "liveness.success": "የፊት ገጽታ በተሳካ ሁኔታ ተረጋግጧል (ነጥብ: {score})",
        "liveness.disclaimer": "ፎቶዎ ለጊዜው ብቻ ተይዞ ባንኩ ካረጋገጠ በኋላ ወዲያውኑ ይሰረዛል።",
        "fields.title": "የባንክ ተጨማሪ መረጃ",
        "fields.btn_continue": "ወደ ፊርማ ይቀጥሉ",
        "fields.err_required": "ይህ መረጃ መሞላት አለበት።",
        "signature.title": "ማመልከቻዎን ይፈርሙ",
        "signature.instruction": "በተዘጋጀው ሳጥን ውስጥ በዲጂታል መንገድ ይፈርሙ",
        "signature.btn_clear": "ፊርማ አጥፋ",
        "signature.btn_submit": "ወደ ባንክ ማዕከላዊ ሲስተም ላክ",
        "signature.err_empty": "እባክዎ ከማስገባትዎ በፊት ትክክለኛ ፊርማ ያስገቡ።",
        "status.processing": "ማመልከቻው ወደ ባንክ ሲስተም በመላክ ላይ ነው...",
        "status.success": "እንኳን ደስ አለዎት! የባንክ አካውንትዎ በተሳካ ሁኔታ ተከፍቷል።",
        "status.account_number": "የአካውንት ቁጥር: {account_number}",
        "status.bank_reference": "የባንክ መለያ: {reference}",
    },
    Locale.OM: {
        "app.title": "Baninsa Herrega Baankii Dijitaalaa Itoophiyaa",
        "app.subtitle": "Waraqaa Eenyummaa Faydaa fayyadamuun herrega baankii bani",
        "step.select_bank": "Baankii Filadhaa",
        "step.consent": "Hayyama Fayyadamaa",
        "step.fayda_input": "Mirkaneessa Faydaa",
        "step.liveness": "Mirkaneessa Fuulaa",
        "step.dynamic_fields": "Odeeffannoo Dabalataa",
        "step.signature": "Mallattoo Dijitaalaa",
        "step.confirmation": "Herregni Banameera",
        "consent.title": "Hayyama Eenyummaa Mirkaneessuu fi Odeeffannoo Qooduu",
        "consent.disclosure_fayda": "Eenyummaa keessan mirkaneessuuf EthSwitch VeriFaydaan Sagantaa Eenyummaa Biyyooleessaa (NIDP) gaafanna.",
        "consent.disclosure_bank": "Odeeffannoon keessan mirkanaa'e gara baankii filattaniitti nageenyaan darba.",
        "consent.device_binding": "Nageenyaaf jecha odeeffannoon meeshaa keessanii ni galmaa'a.",
        "consent.btn_agree": "Walii Galeera; Itti Fufi",
        "consent.btn_refuse": "Hin Barbaadu; Ba'i",
        "consent.refusal_notice": "Hayyamni hin kennamne. Hayyama malee itti fufuun hin danda'amu.",
        "fayda.fin_label": "Lakkoofsa Eenyummaa Faydaa (FIN)",
        "fayda.fin_placeholder": "1234 5678 9012",
        "fayda.fin_helper": "Lakkoofsa Faydaa dijiitii 12 galchaa",
        "fayda.btn_send_otp": "Koodii Mirkaneessaa Ergi",
        "fayda.otp_label": "Koodii SMS dijiitii 6 galchaa",
        "fayda.otp_placeholder": "123456",
        "fayda.otp_timer": "Sekondii {seconds} keessatti lammata ergaa",
        "fayda.btn_verify_otp": "Eenyummaa Mirkaneessi",
        "fayda.err_invalid_fin": "Lakkoofsi FIN dijiitii 12 qofa ta'uu qaba.",
        "fayda.err_invalid_otp": "Koodiin OTP dijiitii 6 ta'uu qaba.",
        "fayda.err_lockout": "Yeroo baay'ee dogoggortaniittu. Maaloo xiqqoo eegaa.",
        "liveness.title": "Mirkaneessa Fuulaa Kallattii",
        "liveness.instruction_center": "Fuula keessan freemii keessa galchaa",
        "liveness.instruction_blink": "Maaloo ija keessan sassaabaa",
        "liveness.instruction_turn": "Fuula keessan gara bitaatti xiqqummaa naannessaa",
        "liveness.instruction_smile": "Fuula ifaan seeqaa",
        "liveness.btn_capture": "Suuraa Kaasaa",
        "liveness.btn_retake": "Irra Deebi'aa Kaasaa",
        "liveness.btn_confirm": "Mirkaneessii Itti Fufi",
        "liveness.success": "Mirkaneessi fuulaa milkaa'eera (Qabxii: {score})",
        "liveness.disclaimer": "Suuraan keessan yeroodhaaf qabama; baankichi mirkaneesseen booda battalatti haqama.",
        "fields.title": "Odeeffannoo Baankii",
        "fields.btn_continue": "Gara Mallattootti Dabrara",
        "fields.err_required": "Dirreen kun dirqama guutamuu qaba.",
        "signature.title": "Iyyata Keessan Mallatteessaa",
        "signature.instruction": "Sanduqa qophaa'e keessatti dijiitaalaan mallatteessaa",
        "signature.btn_clear": "Mallattoo Haqi",
        "signature.btn_submit": "Gara Sirna Baankiitti Ergaa",
        "signature.err_empty": "Maaloo dura mallattoo sirrii galchaa.",
        "status.processing": "Iyyanni gara sirna baankiitti ergamaa jira...",
        "status.success": "Baga Gammaddan! Herregni baankii keessan banameera.",
        "status.account_number": "Lakkoofsa Herregaa: {account_number}",
        "status.bank_reference": "Koodii Baankii: {reference}",
    },
    Locale.TI: {
        "app.title": "ናይ ኢትዮጵያ ዲጂታል ናይ ባንኪ ሒሳብ መኽፈቲ",
        "app.subtitle": "ብፋይዳ ዲጂታል መንነት ሒሳብ ባንኪ ብቐሊሉ ይኽፈቱ",
        "step.select_bank": "ባንኪ ምረጹ",
        "step.consent": "ናይ ፍቓድ ስምምዕ",
        "step.fayda_input": "ምርግጋጽ ፋይዳ",
        "step.liveness": "ምርግጋጽ ገጽ",
        "step.dynamic_fields": "ሓበሬታ ሒሳብ",
        "step.signature": "ዲጂታል ፊርማ",
        "step.confirmation": "ሒሳብ ተኸፊቱ",
        "consent.title": "ስምምዕ ምርግጋጽ መንነትን ምልውዋጥ ሓበሬታን",
        "consent.disclosure_fayda": "መንነትኩም ንምርግጋጽ ብኢትስዊች ቬሪፋይዳ ኣቢልና ካብ ብሔራዊ ፕሮግራም መንነት (NIDP) ሓበሬታ ንረክብ። ባዮሜትሪክኩም ብቐዋምነት ኣይዕቀብን።",
        "consent.disclosure_bank": "ዝተረጋገጸ ሓበሬታኹም ናብቲ ዝመረጽኩምዎ ባንኪ ብውሑስ መንገዲ ይለኣኽ።",
        "consent.device_binding": "ንውሕስነት ተባሂሉ መለለዪ መሳርሒኹም ይምዝገብ።",
        "consent.btn_agree": "ተሰማሚዐ፤ ቀጽል",
        "consent.btn_refuse": "ኣይሰማማዕን፤ ውጻእ",
        "consent.refusal_notice": "ስምምዕ ኣይተረኽበን። ብዘይ ስምምዕ ሒሳብ ምኽፋት ኣይከኣልን።",
        "fayda.fin_label": "ናይ ፋይዳ ቁጽሪ መለለዪ (FIN)",
        "fayda.fin_placeholder": "1234 5678 9012",
        "fayda.fin_helper": "ናይ 12 ኣሃዛት ፋይዳ ቁጽርኹም የእትዉ",
        "fayda.btn_send_otp": "ናይ ምርግጋጽ ኮድ ስደድ",
        "fayda.otp_label": "ብSMS ዝመጸ ናይ 6 ኣሃዝ ኮድ የእትዉ",
        "fayda.otp_placeholder": "123456",
        "fayda.otp_timer": "ብ{seconds} ካልኢት ውሽጢ ደጊምኩም ስደዱ",
        "fayda.btn_verify_otp": "መንነት ኣረጋግጽ",
        "fayda.err_invalid_fin": "ናይ ፋይዳ ቁጽሪ ብትክክል 12 ኣሃዛት ቁጽሪ ክኸውን ኣለዎ።",
        "fayda.err_invalid_otp": "ናይ ምርግጋጽ ኮድ 6 ኣሃዛት ክኸውን ኣለዎ።",
        "fayda.err_lockout": "ተደጋጋሚ ጌጋ ፈተነታት ተገይሩ። በጃኹም ቁሩብ ጸኒሕኩም ፈትኑ።",
        "liveness.title": "ቀጥታዊ ምርግጋጽ ገጽ",
        "liveness.instruction_center": "ገጽኩም ኣብቲ ፍሬም ኣዕርፉ",
        "liveness.instruction_blink": "በጃኹም ዓይንኹም ኣርግብግቡ",
        "liveness.instruction_turn": "ገጽኩም ብቑሩብ ናብ ጸጋም ኣዙሩ",
        "liveness.instruction_smile": "ፍሽኽ በሉ",
        "liveness.btn_capture": "ስእሊ ኣልዕሉ",
        "liveness.btn_retake": "ደጊምኩም ኣልዕሉ",
        "liveness.btn_confirm": "ኣረጋግጽ እሞ ቀጽል",
        "liveness.success": "ምርግጋጽ ገጽ ብዓወት ተፈጺሙ (ነጥቢ: {score})",
        "liveness.disclaimer": "ስእልኹም ንግዜኡ ጥራሕ ተታሒዙ እቲ ባንኪ ምስ ኣረጋገጸ ብኡንብኡ ይድምሰስ።",
        "fields.title": "ናይ ባንኪ ተወሳኺ ሓበሬታ",
        "fields.btn_continue": "ናብ ፊርማ ቀጽል",
        "fields.err_required": "እዚ መስክ እዚ ክምላእ ኣለዎ።",
        "signature.title": "ማመልከቻኹም ፈርሙ",
        "signature.instruction": "ኣብቲ ዝተዳለወ ሳንዱቕ ብዲጂታል ፈርሙ",
        "signature.btn_clear": "ፊርማ ደምስስ",
        "signature.btn_submit": "ናብ ባንኪ ሲስተም ስደድ",
        "signature.err_empty": "ቅድሚ ምልኣኽኩም ትክክለኛ ፊርማ የእትዉ።",
        "status.processing": "ማመልከቻ ናብ ባንኪ ሲስተም ይለኣኽ ኣሎ...",
        "status.success": "እንቋዕ ሓጎሰኩም! ናይ ባንኪ ሒሳብኩም ተኸፊቱ።",
        "status.account_number": "ቁጽሪ ሒሳብ: {account_number}",
        "status.bank_reference": "መወከሲ ባንኪ: {reference}",
    },
}


def get_translation(key: str, locale: Locale | str = Locale.EN, **kwargs: Any) -> str:
    """Retrieve localized string with fallback to English."""
    if isinstance(locale, str):
        try:
            loc = Locale(locale.lower())
        except ValueError:
            loc = Locale.EN
    else:
        loc = locale

    locale_dict = TRANSLATIONS.get(loc, TRANSLATIONS[Locale.EN])
    template = locale_dict.get(key) or TRANSLATIONS[Locale.EN].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            return template
    return template
