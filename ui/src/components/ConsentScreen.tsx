import React, { useState } from 'react';

export interface ConsentScreenProps {
  locale: string;
  onConsentAgreed: (metadata: { deviceFingerprint: string; ipAddress: string }) => void;
  onConsentRefused: () => void;
  t: (key: string) => string;
}

export const ConsentScreen: React.FC<ConsentScreenProps> = ({
  locale,
  onConsentAgreed,
  onConsentRefused,
  t,
}) => {
  const [hasScrolledToBottom, setHasScrolledToBottom] = useState(false);
  const [faydaAcknowledged, setFaydaAcknowledged] = useState(false);
  const [bankAcknowledged, setBankAcknowledged] = useState(false);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    if (scrollTop + clientHeight >= scrollHeight - 20) {
      setHasScrolledToBottom(true);
    }
  };

  const isConsentReady = hasScrolledToBottom && faydaAcknowledged && bankAcknowledged;

  return (
    <article className="consent-card glass-panel" aria-labelledby="consent-heading">
      <header className="consent-header">
        <div className="badge-shield">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="m9 12 2 2 4-4" />
          </svg>
          <span className="badge-text">Sovereign Protection (NIDP §3)</span>
        </div>
        <h2 id="consent-heading" className="consent-title">
          {t('consent.title')}
        </h2>
        <p className="consent-subtitle">
          Please review the plain-language terms regarding how your national ID and application data are handled.
        </p>
      </header>

      <section
        className="disclosure-scroll-box"
        onScroll={handleScroll}
        tabIndex={0}
        role="region"
        aria-label="Consent terms document"
      >
        <div className="disclosure-section">
          <div className="disclosure-icon fayda-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
              <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8zm1-13h-2v6h2zm0 8h-2v2h2z"/>
            </svg>
          </div>
          <div className="disclosure-content">
            <h3>1. National ID Verification (EthSwitch VeriFayda)</h3>
            <p>{t('consent.disclosure_fayda')}</p>
          </div>
        </div>

        <div className="disclosure-section">
          <div className="disclosure-icon bank-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
              <path d="M4 10h16v2H4zm2 4h3v4H6zm5 0h3v4h-3zm5 0h3v4h-3zM2 22h20v-2H2zm10-20L2 6v2h20V6z"/>
            </svg>
          </div>
          <div className="disclosure-content">
            <h3>2. Partner Commercial Bank Transmission</h3>
            <p>{t('consent.disclosure_bank')}</p>
          </div>
        </div>

        <div className="disclosure-section">
          <div className="disclosure-icon device-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
              <rect width="14" height="20" x="5" y="2" rx="2" ry="2" />
              <path d="M12 18h.01" />
            </svg>
          </div>
          <div className="disclosure-content">
            <h3>3. Zero-Retention & Cryptographic Audit</h3>
            <p>{t('consent.device_binding')}</p>
          </div>
        </div>

        {!hasScrolledToBottom && (
          <div className="scroll-hint-indicator" aria-live="polite">
            Scroll down to review full terms ↓
          </div>
        )}
      </section>

      <div className="acknowledgment-controls">
        <label className="checkbox-container">
          <input
            type="checkbox"
            checked={faydaAcknowledged}
            onChange={(e) => setFaydaAcknowledged(e.target.checked)}
            aria-label="Acknowledge Fayda lookup"
          />
          <span className="checkmark" />
          <span className="checkbox-label">
            I authorize query of my national ID record via EthSwitch VeriFayda.
          </span>
        </label>

        <label className="checkbox-container">
          <input
            type="checkbox"
            checked={bankAcknowledged}
            onChange={(e) => setBankAcknowledged(e.target.checked)}
            aria-label="Acknowledge bank transmission"
          />
          <span className="checkmark" />
          <span className="checkbox-label">
            I authorize transmission of my verified profile to the chosen bank.
          </span>
        </label>
      </div>

      <footer className="consent-action-row">
        <button
          type="button"
          className="btn btn-secondary btn-refuse"
          onClick={onConsentRefused}
        >
          {t('consent.btn_refuse')}
        </button>

        <button
          type="button"
          className="btn btn-primary btn-agree"
          disabled={!isConsentReady}
          onClick={() => {
            onConsentAgreed({
              deviceFingerprint: 'client-fp-' + Math.random().toString(36).substring(2, 10),
              ipAddress: '196.188.12.44',
            });
          }}
        >
          {t('consent.btn_agree')}
        </button>
      </footer>
    </article>
  );
};
