import React, { useState } from 'react';

export interface DynamicBankFormProps {
  schema: {
    title?: string;
    required?: string[];
    properties?: Record<string, {
      type: string;
      title?: string;
      enum?: string[];
      minLength?: number;
      maxLength?: number;
      pattern?: string;
      description?: string;
    }>;
  };
  onSubmit: (values: Record<string, any>) => void;
  t: (key: string) => string;
}

export const DynamicBankForm: React.FC<DynamicBankFormProps> = ({
  schema,
  onSubmit,
  t,
}) => {
  const [formValues, setFormValues] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const properties = schema.properties || {};
  const requiredFields = new Set(schema.required || []);

  const handleChange = (name: string, value: any) => {
    setFormValues((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => {
      const copy = { ...prev };
      delete copy[name];
      return copy;
    });
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    for (const [key, prop] of Object.entries(properties)) {
      const val = formValues[key];
      const isRequired = requiredFields.has(key);

      if (isRequired && (val === undefined || val === null || val === '')) {
        newErrors[key] = t('fields.err_required');
        continue;
      }

      if (val && typeof val === 'string') {
        if (prop.minLength && val.length < prop.minLength) {
          newErrors[key] = `Minimum length is ${prop.minLength} characters`;
        }
        if (prop.pattern && !new RegExp(prop.pattern).test(val)) {
          newErrors[key] = `Invalid format (${prop.description || prop.pattern})`;
        }
      }
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate()) {
      onSubmit(formValues);
    }
  };

  return (
    <form className="dynamic-bank-form glass-panel" onSubmit={handleSubmit} noValidate>
      <header className="form-header">
        <h2 className="form-title">{t('fields.title')}</h2>
        <p className="form-subtitle">
          Please provide the bank-specific KYC attributes required for your chosen account tier.
        </p>
      </header>

      <div className="dynamic-fields-grid">
        {Object.entries(properties).map(([name, prop]) => {
          const isRequired = requiredFields.has(name);
          const fieldError = errors[name];

          return (
            <div key={name} className="form-group">
              <label htmlFor={`dynamic-${name}`} className="input-label">
                {prop.title || name}
                {isRequired && <span className="required-star">*</span>}
              </label>

              {prop.enum ? (
                <select
                  id={`dynamic-${name}`}
                  className={`text-input select-input ${fieldError ? 'input-error' : ''}`}
                  value={formValues[name] || ''}
                  onChange={(e) => handleChange(name, e.target.value)}
                  aria-required={isRequired}
                >
                  <option value="">Select an option...</option>
                  {prop.enum.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id={`dynamic-${name}`}
                  type={prop.type === 'integer' || prop.type === 'number' ? 'number' : 'text'}
                  className={`text-input ${fieldError ? 'input-error' : ''}`}
                  placeholder={prop.description || ''}
                  value={formValues[name] || ''}
                  onChange={(e) => handleChange(name, e.target.value)}
                  aria-required={isRequired}
                />
              )}

              {fieldError && <span className="error-text" role="alert">{fieldError}</span>}
            </div>
          );
        })}
      </div>

      <footer className="form-footer">
        <button type="submit" className="btn btn-primary btn-block">
          {t('fields.btn_continue')}
        </button>
      </footer>
    </form>
  );
};
