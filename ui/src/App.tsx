import React, { useState } from 'react';
import { ConsentScreen } from './components/ConsentScreen';
import { FaydaVerification } from './components/FaydaVerification';
import { LivenessCapture } from './components/LivenessCapture';
import { DynamicBankForm } from './components/DynamicBankForm';

export type SupportedLocale = 'en' | 'am' | 'om' | 'ti';

export type OnboardingStep =
  | 'SELECT_BANK'
  | 'CONSENT'
  | 'FAYDA_FIN'
  | 'LIVENESS'
  | 'DYNAMIC_FIELDS'
  | 'SIGNATURE'
  | 'SUBMITTING'
  | 'CONFIRMED'
  | 'REFUSED';

const TRANSLATIONS: Record<SupportedLocale, Record<string, string>> = {
  en: {
    'app.title': 'Ethiopian eKYC Digital Bank Onboarding',
    'app.subtitle': 'Open your sovereign bank account with verified Fayda ID',
    'step.select_bank': 'Select Bank',
    'step.consent': 'Consent',
    'step.fayda_input': 'Fayda ID',
    'step.liveness': 'Face Liveness',
    'step.dynamic_fields': 'Account Data',
    'step.signature': 'Signature',
    'consent.title': 'Consent to Identity Verification & Data Sharing',
    'consent.disclosure_fayda': 'We query the National ID Program (NIDP) via EthSwitch VeriFayda to confirm your legal identity using your 12-digit FIN. Your biometric vectors and raw credentials are never permanently stored.',
    'consent.disclosure_bank': 'Your verified demographic details (full name, date of birth, gender, and photograph) along with dynamic application data will be securely transmitted to your chosen commercial bank.',
    'consent.device_binding': 'Client device fingerprint and session metadata are cryptographically logged for fraud prevention.',
    'consent.btn_agree': 'Agree & Continue',
    'consent.btn_refuse': 'Decline & Exit',
    'consent.refusal_notice': 'Consent was declined. You cannot proceed with digital onboarding without consent.',
    'fayda.fin_label': 'Fayda National ID Number (FIN)',
    'fayda.fin_helper': 'Enter your 12-digit National Identification Number',
    'fayda.btn_send_otp': 'Send Verification OTP',
    'fayda.otp_label': 'Enter 6-digit SMS OTP',
    'fayda.otp_timer': 'Resend code in {seconds}s',
    'fayda.btn_verify_otp': 'Verify Identity',
    'fayda.err_invalid_fin': 'FIN must be exactly 12 numeric digits.',
    'fayda.err_invalid_otp': 'OTP must be 6 numeric digits.',
    'fayda.err_lockout': 'Too many failed attempts. Identity verification is temporarily locked.',
    'liveness.title': 'Facial Liveness & Identity Verification',
    'liveness.instruction_center': 'Center your face inside the oval frame',
    'liveness.instruction_blink': 'Please blink your eyes naturally',
    'liveness.btn_capture': 'Capture Selfie',
    'liveness.btn_retake': 'Retake Photo',
    'liveness.btn_confirm': 'Confirm & Proceed',
    'liveness.success': 'Liveness check passed successfully (Score: {score})',
    'liveness.disclaimer': 'Selfie frames are held in ephemeral memory and discarded immediately after bank confirmation.',
    'fields.title': 'Bank-Specific Information',
    'fields.btn_continue': 'Continue to Signature',
    'fields.err_required': 'This field is required.',
  },
  am: {
    'app.title': 'የኢትዮጵያ ዲጂታል የባንክ አካውንት መክፈቻ',
    'app.subtitle': 'በፋይዳ ዲጂታል መታወቂያዎ አማካኝነት በደቂቃዎች ውስጥ አካውንት ይክፈቱ',
    'step.select_bank': 'ባንክ ይምረጡ',
    'step.consent': 'ስምምነት',
    'step.fayda_input': 'ፋይዳ መታወቂያ',
    'step.liveness': 'የፊት ገጽታ',
    'step.dynamic_fields': 'የባንክ መረጃ',
    'step.signature': 'ዲጂታል ፊርማ',
    'consent.title': 'የግል መረጃ ማረጋገጫ እና ማጋሪያ ስምምነት',
    'consent.disclosure_fayda': 'የእርስዎን ህጋዊ ማንነት ለማረጋገጥ በኢትስዊች ቬሪፋይዳ በኩል ከብሔራዊ መታወቂያ ፕሮግራም ጋር እንገናኛለን።',
    'consent.disclosure_bank': 'የተረጋገጠው መረጃዎ ለመረጡት ባንክ በደህንነት ይተላለፋል።',
    'consent.device_binding': 'የመሳሪያዎ መለያ መረጃ ለደህንነት ይመዘገባል።',
    'consent.btn_agree': 'ተስማምቻለሁ፤ ይቀጥሉ',
    'consent.btn_refuse': 'አልስማማም፤ ውጣ',
    'consent.refusal_notice': 'ስምምነት አልተደረገም። ያለስምምነት አካውንት መክፈት አይቻልም።',
    'fayda.fin_label': 'የፋይዳ ብሔራዊ መታወቂያ ቁጥር (FIN)',
    'fayda.fin_helper': 'ባለ 12 አሃዝ የፋይዳ ቁጥርዎን ያስገቡ',
    'fayda.btn_send_otp': 'የማረጋገጫ ኮድ ላክ',
    'fayda.otp_label': 'በSMS የተላከውን ባለ 6 አሃዝ ኮድ ያስገቡ',
    'fayda.otp_timer': 'ኮዱን በ{seconds} ሰከንድ ውስጥ እንደገና ይላኩ',
    'fayda.btn_verify_otp': 'ማንነትን አረጋግጥ',
    'fayda.err_invalid_fin': 'የፋይዳ ቁጥር በትክክል 12 የቁጥር አሃዞች መሆን አለበት።',
    'fayda.err_invalid_otp': 'የማረጋገጫ ኮድ ባለ 6 አሃዝ መሆን አለበት።',
    'fayda.err_lockout': 'ተደጋጋሚ የተሳሳተ ሙከራ ተደርጓል። እባክዎ ትንሽ ቆይተው ይሞክሩ።',
    'liveness.title': 'የፊት ገጽታ የቀጥታ ማረጋገጫ',
    'liveness.instruction_center': 'ፊትዎን በክቡ ማዕቀፍ ውስጥ ያስተካክሉ',
    'liveness.instruction_blink': 'እባክዎን ዓይንዎን ያርገብግቡ',
    'liveness.btn_capture': 'ፎቶ አንሳ',
    'liveness.btn_retake': 'እንደገና አንሳ',
    'liveness.btn_confirm': 'አረጋግጥና ቀጥል',
    'liveness.success': 'የፊት ገጽታ በተሳካ ሁኔታ ተረጋግጧል (ነጥብ: {score})',
    'liveness.disclaimer': 'ፎቶዎ ለጊዜው ብቻ ተይዞ ባንኩ ካረጋገጠ በኋላ ወዲያውኑ ይሰረዛል።',
    'fields.title': 'የባንክ ተጨማሪ መረጃ',
    'fields.btn_continue': 'ወደ ፊርማ ይቀጥሉ',
    'fields.err_required': 'ይህ መረጃ መሞላት አለበት።',
  },
  om: {
    'app.title': 'Baninsa Herrega Baankii Dijitaalaa Itoophiyaa',
    'app.subtitle': 'Waraqaa Eenyummaa Faydaa fayyadamuun herrega baankii bani',
    'step.select_bank': 'Baankii Filadhaa',
    'step.consent': 'Hayyama',
    'step.fayda_input': 'Faydaa ID',
    'step.liveness': 'Fuula',
    'step.dynamic_fields': 'Odeeffannoo',
    'step.signature': 'Mallattoo',
    'consent.title': 'Hayyama Eenyummaa Mirkaneessuu fi Odeeffannoo Qooduu',
    'consent.disclosure_fayda': 'Eenyummaa keessan mirkaneessuuf EthSwitch VeriFaydaan NIDP gaafanna.',
    'consent.disclosure_bank': 'Odeeffannoon keessan mirkanaa\'e gara baankii filattaniitti darba.',
    'consent.device_binding': 'Nageenyaaf jecha odeeffannoon meeshaa ni galmaa\'a.',
    'consent.btn_agree': 'Walii Galeera; Itti Fufi',
    'consent.btn_refuse': 'Hin Barbaadu; Ba\'i',
    'consent.refusal_notice': 'Hayyamni hin kennamne. Hayyama malee itti fufuun hin danda\'amu.',
    'fayda.fin_label': 'Lakkoofsa Eenyummaa Faydaa (FIN)',
    'fayda.fin_helper': 'Lakkoofsa Faydaa dijiitii 12 galchaa',
    'fayda.btn_send_otp': 'Koodii Ergi',
    'fayda.otp_label': 'Koodii SMS dijiitii 6 galchaa',
    'fayda.otp_timer': 'Sekondii {seconds} keessatti lammata ergaa',
    'fayda.btn_verify_otp': 'Mirkaneessi',
    'fayda.err_invalid_fin': 'FIN dijiitii 12 qofa ta\'uu qaba.',
    'fayda.err_invalid_otp': 'Koodiin dijiitii 6 ta\'uu qaba.',
    'fayda.err_lockout': 'Yeroo baay\'ee dogoggortaniittu.',
    'liveness.title': 'Mirkaneessa Fuulaa Kallattii',
    'liveness.instruction_center': 'Fuula keessan freemii keessa galchaa',
    'liveness.instruction_blink': 'Maaloo ija keessan sassaabaa',
    'liveness.btn_capture': 'Suuraa Kaasaa',
    'liveness.btn_retake': 'Irra Deebi\'aa Kaasaa',
    'liveness.btn_confirm': 'Mirkaneessii Itti Fufi',
    'liveness.success': 'Mirkaneessi fuulaa milkaa\'eera ({score})',
    'liveness.disclaimer': 'Suuraan yeroodhaaf qabama; battalatti haqama.',
    'fields.title': 'Odeeffannoo Baankii',
    'fields.btn_continue': 'Gara Mallattootti',
    'fields.err_required': 'Dirqama guutamuu qaba.',
  },
  ti: {
    'app.title': 'ናይ ኢትዮጵያ ዲጂታል ናይ ባንኪ ሒሳብ መኽፈቲ',
    'app.subtitle': 'ብፋይዳ ዲጂታል መንነት ሒሳብ ባንኪ ብቐሊሉ ይኽፈቱ',
    'step.select_bank': 'ባንኪ ምረጹ',
    'step.consent': 'ስምምዕ',
    'step.fayda_input': 'ፋይዳ',
    'step.liveness': 'ገጽ',
    'step.dynamic_fields': 'ሓበሬታ',
    'step.signature': 'ፊርማ',
    'consent.title': 'ስምምዕ ምርግጋጽ መንነትን ምልውዋጥ ሓበሬታን',
    'consent.disclosure_fayda': 'መንነትኩም ንምርግጋጽ ብኢትስዊች ቬሪፋይዳ ኣቢልና ንረክብ።',
    'consent.disclosure_bank': 'ዝተረጋገጸ ሓበሬታኹም ናብቲ ዝመረጽኩምዎ ባንኪ ይለኣኽ።',
    'consent.device_binding': 'ንውሕስነት ተባሂሉ መለለዪ መሳርሒኹም ይምዝገብ።',
    'consent.btn_agree': 'ተሰማሚዐ፤ ቀጽል',
    'consent.btn_refuse': 'ኣይሰማማዕን፤ ውጻእ',
    'consent.refusal_notice': 'ስምምዕ ኣይተረኽበን። ብዘይ ስምምዕ ሒሳብ ምኽፋት ኣይከኣልን።',
    'fayda.fin_label': 'ናይ ፋይዳ ቁጽሪ መለለዪ (FIN)',
    'fayda.fin_helper': 'ናይ 12 ኣሃዛት ፋይዳ ቁጽርኹም የእትዉ',
    'fayda.btn_send_otp': 'ኮድ ስደድ',
    'fayda.otp_label': 'ናይ 6 ኣሃዝ ኮድ የእትዉ',
    'fayda.otp_timer': 'ብ{seconds} ካልኢት ውሽጢ ደጊምኩም ስደዱ',
    'fayda.btn_verify_otp': 'ኣረጋግጽ',
    'fayda.err_invalid_fin': 'ናይ ፋይዳ ቁጽሪ 12 ኣሃዛት ክኸውን ኣለዎ።',
    'fayda.err_invalid_otp': 'ኮድ 6 ኣሃዛት ክኸውን ኣለዎ።',
    'fayda.err_lockout': 'ተደጋጋሚ ጌጋ ፈተነታት ተገይሩ።',
    'liveness.title': 'ቀጥታዊ ምርግጋጽ ገጽ',
    'liveness.instruction_center': 'ገጽኩም ኣብቲ ፍሬም ኣዕርፉ',
    'liveness.instruction_blink': 'በጃኹም ዓይንኹም ኣርግብግቡ',
    'liveness.btn_capture': 'ስእሊ ኣልዕሉ',
    'liveness.btn_retake': 'ደጊምኩም ኣልዕሉ',
    'liveness.btn_confirm': 'ኣረጋግጽ እሞ ቀጽል',
    'liveness.success': 'ምርግጋጽ ገጽ ብዓወት ተፈጺሙ ({score})',
    'liveness.disclaimer': 'ስእልኹም ብኡንብኡ ይድምሰስ።',
    'fields.title': 'ናይ ባንኪ ተወሳኺ ሓበሬታ',
    'fields.btn_continue': 'ናብ ፊርማ ቀጽል',
    'fields.err_required': 'እዚ መስክ እዚ ክምላእ ኣለዎ።',
  },
};

export const App: React.FC = () => {
  const [locale, setLocale] = useState<SupportedLocale>('en');
  const [step, setStep] = useState<OnboardingStep>('SELECT_BANK');
  const [selectedBank, setSelectedBank] = useState<string>('awash');
  const [selectedTier, setSelectedTier] = useState<string>('standard');
  const [finNumber, setFinNumber] = useState<string>('');
  const [signatureText, setSignatureText] = useState<string>('');
  const [issuedAccount, setIssuedAccount] = useState<{ accountNumber: string; reference: string } | null>(null);

  const t = (key: string, params?: Record<string, any>): string => {
    let str = TRANSLATIONS[locale][key] || TRANSLATIONS.en[key] || key;
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        str = str.replace(`{${k}}`, String(v));
      });
    }
    return str;
  };

  const stepsList: { key: OnboardingStep; label: string }[] = [
    { key: 'SELECT_BANK', label: t('step.select_bank') },
    { key: 'CONSENT', label: t('step.consent') },
    { key: 'FAYDA_FIN', label: t('step.fayda_input') },
    { key: 'LIVENESS', label: t('step.liveness') },
    { key: 'DYNAMIC_FIELDS', label: t('step.dynamic_fields') },
    { key: 'SIGNATURE', label: t('step.signature') },
  ];

  const handleBankSelect = (bankId: string, tier: string) => {
    setSelectedBank(bankId);
    setSelectedTier(tier);
    setStep('CONSENT');
  };

  const handleConsentAgreed = () => {
    setStep('FAYDA_FIN');
  };

  const handleConsentRefused = () => {
    setStep('REFUSED');
  };

  const handleFaydaVerified = (fin: string) => {
    setFinNumber(fin);
    setStep('LIVENESS');
  };

  const handleLivenessDone = () => {
    setStep('DYNAMIC_FIELDS');
  };

  const handleDynamicFieldsDone = () => {
    setStep('SIGNATURE');
  };

  const handleSignatureSubmit = () => {
    if (!signatureText.trim()) return;
    setStep('SUBMITTING');
    setTimeout(() => {
      setIssuedAccount({
        accountNumber: 'AWASH-100293847',
        reference: 'CBS-TXN-984712',
      });
      setStep('CONFIRMED');
    }, 1200);
  };

  return (
    <div className="app-shell dark-theme">
      <header className="top-nav-bar">
        <div className="nav-brand">
          <span className="brand-logo-gem">🛡️</span>
          <div className="brand-titles">
            <h1 className="brand-title">{t('app.title')}</h1>
            <span className="brand-subtitle">{t('app.subtitle')}</span>
          </div>
        </div>

        <div className="locale-selector">
          <label htmlFor="locale-select" className="sr-only">Choose Language</label>
          <select
            id="locale-select"
            className="locale-dropdown"
            value={locale}
            onChange={(e) => setLocale(e.target.value as SupportedLocale)}
            aria-label="Language selection"
          >
            <option value="en">English (EN)</option>
            <option value="am">አማርኛ (Amharic)</option>
            <option value="om">Afaan Oromoo</option>
            <option value="ti">ትግርኛ (Tigrinya)</option>
          </select>
        </div>
      </header>

      {step !== 'CONFIRMED' && step !== 'REFUSED' && (
        <nav className="stepper-progress-bar" aria-label="Onboarding Progress">
          <ol className="stepper-track">
            {stepsList.map((s, idx) => {
              const isCurrent = s.key === step;
              const isDone = stepsList.findIndex((item) => item.key === step) > idx;
              return (
                <li
                  key={s.key}
                  className={`stepper-step ${isCurrent ? 'step-current' : ''} ${isDone ? 'step-done' : ''}`}
                >
                  <div className="step-number-circle">
                    {isDone ? '✓' : idx + 1}
                  </div>
                  <span className="step-label">{s.label}</span>
                </li>
              );
            })}
          </ol>
        </nav>
      )}

      <main className="main-viewport-content">
        {step === 'SELECT_BANK' && (
          <section className="bank-selection-card glass-panel" aria-labelledby="bank-select-heading">
            <h2 id="bank-select-heading" className="panel-title">Choose Partner Commercial Bank</h2>
            <div className="bank-options-grid">
              <div
                className={`bank-tile ${selectedBank === 'awash' ? 'tile-active' : ''}`}
                onClick={() => handleBankSelect('awash', 'standard')}
                tabIndex={0}
                role="button"
                onKeyDown={(e) => e.key === 'Enter' && handleBankSelect('awash', 'standard')}
              >
                <div className="bank-logo-badge">AWASH</div>
                <div className="bank-info">
                  <h3>Awash Bank</h3>
                  <p>Standard Savings & Premier Account</p>
                </div>
                <button type="button" className="btn btn-outline">Select Awash</button>
              </div>

              <div
                className={`bank-tile ${selectedBank === 'cbe' ? 'tile-active' : ''}`}
                onClick={() => handleBankSelect('cbe', 'standard')}
                tabIndex={0}
                role="button"
                onKeyDown={(e) => e.key === 'Enter' && handleBankSelect('cbe', 'standard')}
              >
                <div className="bank-logo-badge cbe-badge">CBE</div>
                <div className="bank-info">
                  <h3>Commercial Bank of Ethiopia</h3>
                  <p>National Sovereign Retail Banking</p>
                </div>
                <button type="button" className="btn btn-outline">Select CBE</button>
              </div>
            </div>
          </section>
        )}

        {step === 'CONSENT' && (
          <ConsentScreen
            locale={locale}
            onConsentAgreed={handleConsentAgreed}
            onConsentRefused={handleConsentRefused}
            t={t}
          />
        )}

        {step === 'FAYDA_FIN' && (
          <FaydaVerification
            locale={locale}
            onVerificationComplete={handleFaydaVerified}
            t={t}
          />
        )}

        {step === 'LIVENESS' && (
          <LivenessCapture
            locale={locale}
            onLivenessComplete={handleLivenessDone}
            t={t}
          />
        )}

        {step === 'DYNAMIC_FIELDS' && (
          <DynamicBankForm
            schema={{
              title: 'Awash Bank Intake',
              required: ['mother_maiden_name', 'occupation'],
              properties: {
                mother_maiden_name: {
                  type: 'string',
                  title: "Mother's Maiden Name",
                  minLength: 2,
                },
                occupation: {
                  type: 'string',
                  title: 'Line of Work',
                  enum: ['Employed', 'Self-Employed', 'Student', 'Merchant'],
                },
                tin_number: {
                  type: 'string',
                  title: 'Tax Identification Number (TIN)',
                  pattern: '^\\d{10}$',
                  description: '10 numeric digits',
                },
              },
            }}
            onSubmit={handleDynamicFieldsDone}
            t={t}
          />
        )}

        {step === 'SIGNATURE' && (
          <section className="signature-card glass-panel" aria-labelledby="sig-heading">
            <h2 id="sig-heading" className="panel-title">Digital Signature & Submission</h2>
            <p className="panel-desc">Sign your application to authorize account creation with {selectedBank.toUpperCase()}.</p>

            <div className="signature-pad-wrapper">
              <label htmlFor="signature-input" className="input-label">Draw or Type Legal Signature</label>
              <input
                id="signature-input"
                type="text"
                className="text-input signature-input"
                placeholder="Type your full legal signature..."
                value={signatureText}
                onChange={(e) => setSignatureText(e.target.value)}
              />
            </div>

            <button
              type="button"
              className="btn btn-primary btn-block"
              disabled={!signatureText.trim()}
              onClick={handleSignatureSubmit}
            >
              Submit Application to Core Banking System
            </button>
          </section>
        )}

        {step === 'SUBMITTING' && (
          <div className="loading-card glass-panel" aria-live="polite">
            <div className="spinner-orbit" />
            <h2>Packaging Sovereign Application...</h2>
            <p>HMAC-signing payload, dispatching to Redis Streams & Bank Core Banking System.</p>
          </div>
        )}

        {step === 'CONFIRMED' && issuedAccount && (
          <section className="confirmation-card glass-panel" aria-labelledby="conf-heading">
            <div className="success-badge-icon">✓</div>
            <h2 id="conf-heading" className="conf-title">Account Successfully Opened!</h2>
            <p className="conf-subtitle">Your identity has been sovereignly verified via Fayda.</p>

            <div className="account-details-box">
              <div className="detail-row">
                <span className="detail-label">Issued Account Number:</span>
                <span className="detail-value">{issuedAccount.accountNumber}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">CBS Reference Code:</span>
                <span className="detail-value">{issuedAccount.reference}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Fayda National ID:</span>
                <span className="detail-value">{finNumber ? `•••• •••• ${finNumber.slice(-4)}` : 'Verified'}</span>
              </div>
            </div>

            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setStep('SELECT_BANK');
                setFinNumber('');
                setSignatureText('');
              }}
            >
              Start New Onboarding Session
            </button>
          </section>
        )}

        {step === 'REFUSED' && (
          <section className="refusal-card glass-panel" aria-labelledby="refusal-heading">
            <div className="error-badge-icon">✕</div>
            <h2 id="refusal-heading" className="panel-title">Onboarding Session Terminated</h2>
            <p className="refusal-notice">{t('consent.refusal_notice')}</p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setStep('SELECT_BANK')}
            >
              Return to Bank Selection
            </button>
          </section>
        )}
      </main>
    </div>
  );
};

export default App;
