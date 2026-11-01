import React, { useState } from 'react';

export interface LivenessCaptureProps {
  locale: string;
  onLivenessComplete: (selfieBase64: string, score: number) => void;
  t: (key: string, params?: Record<string, any>) => string;
}

export const LivenessCapture: React.FC<LivenessCaptureProps> = ({
  locale,
  onLivenessComplete,
  t,
}) => {
  const [stage, setStage] = useState<'ALIGNING' | 'CHALLENGE' | 'CAPTURED' | 'EVALUATING' | 'PASSED' | 'FAILED'>('ALIGNING');
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [livenessScore, setLivenessScore] = useState<number>(0);

  const handleStartCapture = () => {
    setStage('CHALLENGE');
    setTimeout(() => {
      // Simulate live anti-spoofing frame grab
      const dummySelfie = 'data:image/jpeg;base64,' + btoa('dummy-selfie-frame-stream-data-vector-buffer');
      setCapturedImage(dummySelfie);
      setStage('CAPTURED');
    }, 1200);
  };

  const handleConfirmLiveness = () => {
    setStage('EVALUATING');
    setTimeout(() => {
      const score = 0.96;
      setLivenessScore(score);
      setStage('PASSED');
      onLivenessComplete(capturedImage || '', score);
    }, 800);
  };

  const handleRetake = () => {
    setCapturedImage(null);
    setStage('ALIGNING');
  };

  return (
    <article className="liveness-card glass-panel" aria-labelledby="liveness-heading">
      <header className="liveness-header">
        <div className="badge-shield security-badge">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="3" />
            <path d="M3 7V5a2 2 0 0 1 2-2h2m10 0h2a2 2 0 0 1 2 2v2m0 10v2a2 2 0 0 1-2 2h-2m-10 0H5a2 2 0 0 1-2-2v-2" />
          </svg>
          <span className="badge-text">Biometric Anti-Spoofing</span>
        </div>
        <h2 id="liveness-heading" className="liveness-title">
          {t('liveness.title')}
        </h2>
        <p className="liveness-subtitle">
          {stage === 'ALIGNING' && t('liveness.instruction_center')}
          {stage === 'CHALLENGE' && t('liveness.instruction_blink')}
          {stage === 'CAPTURED' && 'Review your selfie before biometric matching'}
          {stage === 'EVALUATING' && 'Analyzing 3D facial depth & anti-spoofing...'}
          {stage === 'PASSED' && t('liveness.success', { score: livenessScore })}
        </p>
      </header>

      <div className="camera-viewfinder-container">
        <div className={`camera-viewfinder stage-${stage.toLowerCase()}`}>
          {capturedImage ? (
            <img src={capturedImage} alt="Captured face selfie" className="captured-preview" />
          ) : (
            <div className="simulated-camera-feed">
              <div className="face-oval-guide">
                <div className="oval-bracket bracket-tl" />
                <div className="oval-bracket bracket-tr" />
                <div className="oval-bracket bracket-bl" />
                <div className="oval-bracket bracket-br" />
                {stage === 'CHALLENGE' && <div className="scanning-laser-line" />}
              </div>
            </div>
          )}

          <div className="viewfinder-overlay-badges">
            <span className={`status-pill pill-${stage.toLowerCase()}`}>
              {stage === 'ALIGNING' && 'Aligning Face'}
              {stage === 'CHALLENGE' && 'Detecting Blink'}
              {stage === 'CAPTURED' && 'Frame Captured'}
              {stage === 'EVALUATING' && 'Evaluating...'}
              {stage === 'PASSED' && '✓ Liveness Verified'}
            </span>
          </div>
        </div>

        <p className="privacy-disclaimer">
          🔒 {t('liveness.disclaimer')}
        </p>
      </div>

      <footer className="liveness-actions">
        {stage === 'ALIGNING' && (
          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={handleStartCapture}
          >
            {t('liveness.btn_capture')}
          </button>
        )}

        {stage === 'CAPTURED' && (
          <div className="action-button-group">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleRetake}
            >
              {t('liveness.btn_retake')}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleConfirmLiveness}
            >
              {t('liveness.btn_confirm')}
            </button>
          </div>
        )}

        {stage === 'PASSED' && (
          <div className="passed-badge-banner">
            <span>🎉 Anti-spoofing match verified</span>
          </div>
        )}
      </footer>
    </article>
  );
};
