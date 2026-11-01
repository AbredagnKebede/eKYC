import React, { useState, useEffect } from 'react';

export interface FaydaVerificationProps {
  locale: string;
  onVerificationComplete: (fin: string, otp: string) => void;
  t: (key: string, params?: Record<string, any>) => string;
}

export const FaydaVerification: React.FC<FaydaVerificationProps> = ({
  locale,
  onVerificationComplete,
  t,
}) => {
  const [finRaw, setFinRaw] = useState('');
  const [finError, setFinError] = useState<string | null>(null);
  const [otpStage, setOtpStage] = useState<'IDLE' | 'OTP_SENT' | 'VERIFYING'>('IDLE');
  const [otpCode, setOtpCode] = useState('');
  const [otpError, setOtpError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(60);
  const [isLockedOut, setIsLockedOut] = useState(false);
  const [attempts, setAttempts] = useState(0);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (otpStage === 'OTP_SENT' && countdown > 0) {
      timer = setInterval(() => setCountdown((prev) => prev - 1), 1000);
    }
    return () => clearInterval(timer);
  }, [otpStage, countdown]);

  const cleanFin = (val: string) => val.replace(/\D/g, '').slice(0, 12);

  const formatFinDisplay = (val: string) => {
    const digits = cleanFin(val);
    const parts = [];
    for (let i = 0; i < digits.length; i += 4) {
      parts.push(digits.slice(i, i + 4));
    }
    return parts.join(' ');
  };

  const handleFinChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const cleaned = cleanFin(e.target.value);
    setFinRaw(cleaned);
    setFinError(null);
  };

  const handleSendOtp = () => {
    if (isLockedOut) return;
    if (finRaw.length !== 12) {
      setFinError(t('fayda.err_invalid_fin'));
      return;
    }
    setOtpStage('OTP_SENT');
    setCountdown(60);
    setOtpError(null);
  };

  const handleResendOtp = () => {
    if (countdown > 0 || isLockedOut) return;
    setCountdown(60);
    setOtpError(null);
  };

  const handleVerifyOtp = () => {
    if (isLockedOut) return;
    const cleanedOtp = otpCode.replace(/\D/g, '');
    if (cleanedOtp.length !== 6) {
      const nextAttempts = attempts + 1;
      setAttempts(nextAttempts);
      if (nextAttempts >= 3) {
        setIsLockedOut(true);
        setOtpError(t('fayda.err_lockout'));
      } else {
        setOtpError(t('fayda.err_invalid_otp'));
      }
      return;
    }

    setOtpStage('VERIFYING');
    onVerificationComplete(finRaw, cleanedOtp);
  };

  return (
    <article className="fayda-card glass-panel" aria-labelledby="fayda-heading">
      <header className="fayda-header">
        <div className="national-id-badge">
          <span className="badge-flag">🇪🇹</span>
          <span className="badge-text">Fayda VeriFayda 2.0</span>
        </div>
        <h2 id="fayda-heading" className="fayda-title">
          {t('step.fayda_input')}
        </h2>
        <p className="fayda-subtitle">
          {t('fayda.fin_helper')}
        </p>
      </header>

      {isLockedOut ? (
        <div className="alert-box alert-error" role="alert">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2zm0-4h-2V7h2z" />
          </svg>
          <div className="alert-content">
            <strong>Verification Locked</strong>
            <p>{t('fayda.err_lockout')}</p>
          </div>
        </div>
      ) : (
        <div className="fayda-form-body">
          <div className="form-group">
            <label htmlFor="fin-input" className="input-label">
              {t('fayda.fin_label')}
            </label>
            <div className="fin-input-wrapper">
              <input
                id="fin-input"
                type="text"
                inputMode="numeric"
                className={`text-input fin-input ${finError ? 'input-error' : ''}`}
                placeholder="1234 5678 9012"
                value={formatFinDisplay(finRaw)}
                onChange={handleFinChange}
                disabled={otpStage !== 'IDLE'}
                autoComplete="off"
                aria-describedby={finError ? 'fin-error-text' : undefined}
              />
              <span className="digit-counter">{finRaw.length}/12</span>
            </div>
            {finError && (
              <span id="fin-error-text" className="error-text" role="alert">
                {finError}
              </span>
            )}
          </div>

          {otpStage === 'IDLE' ? (
            <button
              type="button"
              className="btn btn-primary btn-block"
              disabled={finRaw.length !== 12}
              onClick={handleSendOtp}
            >
              {t('fayda.btn_send_otp')}
            </button>
          ) : (
            <section className="otp-verification-section" aria-label="OTP verification form">
              <div className="form-group">
                <div className="otp-header-row">
                  <label htmlFor="otp-input" className="input-label">
                    {t('fayda.otp_label')}
                  </label>
                  <span className="timer-badge">
                    {countdown > 0 ? (
                      t('fayda.otp_timer', { seconds: countdown })
                    ) : (
                      <button
                        type="button"
                        className="btn-link"
                        onClick={handleResendOtp}
                      >
                        Resend Code
                      </button>
                    )}
                  </span>
                </div>
                <input
                  id="otp-input"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  className={`text-input otp-input ${otpError ? 'input-error' : ''}`}
                  placeholder="••••••"
                  value={otpCode}
                  onChange={(e) => {
                    setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6));
                    setOtpError(null);
                  }}
                  aria-describedby={otpError ? 'otp-error-text' : undefined}
                />
                {otpError && (
                  <span id="otp-error-text" className="error-text" role="alert">
                    {otpError}
                  </span>
                )}
              </div>

              <button
                type="button"
                className="btn btn-primary btn-block"
                disabled={otpCode.length !== 6 || otpStage === 'VERIFYING'}
                onClick={handleVerifyOtp}
              >
                {otpStage === 'VERIFYING' ? 'Verifying...' : t('fayda.btn_verify_otp')}
              </button>
            </section>
          )}
        </div>
      )}
    </article>
  );
};
