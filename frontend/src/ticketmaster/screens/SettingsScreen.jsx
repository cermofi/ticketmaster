import React, { useEffect, useState } from 'react';
import { FormGroup, Input, Label } from 'reactstrap';

import AuthGate from './AuthGate.jsx';
import { PageHeader } from './helpers.jsx';

const defaults = {
  density: 'comfortable',
  contrast: 'default',
  reduceMotion: false
};

export default function SettingsScreen() {
  return (
    <AuthGate>
      {() => <Settings />}
    </AuthGate>
  );
}

function Settings() {
  const [settings, setSettings] = useState(() => {
    try {
      return { ...defaults, ...JSON.parse(localStorage.getItem('ticketmaster.gui') || '{}') };
    } catch {
      return defaults;
    }
  });

  useEffect(() => {
    localStorage.setItem('ticketmaster.gui', JSON.stringify(settings));
    document.body.dataset.tmDensity = settings.density;
    document.body.dataset.tmContrast = settings.contrast;
    document.body.classList.toggle('tm-reduce-motion', settings.reduceMotion);
  }, [settings]);

  const update = (key, value) => setSettings({ ...settings, [key]: value });

  return (
    <div className="tm-screen">
      <PageHeader title="Nastavení">
        Local preferences for this browser.
      </PageHeader>
      <section className="tm-form-page">
        <FormGroup>
          <Label>Hustota rozhraní</Label>
          <Input type="select" value={settings.density} onChange={(event) => update('density', event.target.value)}>
            <option value="comfortable">Comfortable</option>
            <option value="compact">Compact</option>
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Kontrast</Label>
          <Input type="select" value={settings.contrast} onChange={(event) => update('contrast', event.target.value)}>
            <option value="default">Default</option>
            <option value="high">High contrast</option>
          </Input>
        </FormGroup>
        <div className="tm-switch-row">
          <span>Omezit animace</span>
          <button
            type="button"
            className={`tm-switch ${settings.reduceMotion ? 'is-on' : ''}`}
            role="switch"
            aria-checked={settings.reduceMotion}
            onClick={() => update('reduceMotion', !settings.reduceMotion)}
          >
            <span />
          </button>
        </div>
      </section>
    </div>
  );
}
