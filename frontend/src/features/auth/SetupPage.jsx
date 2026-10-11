import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Stack, TextField } from '@mui/material';
import { useAuth } from '../../app/AuthContext';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { BareShell } from '../../components/AppShell';
import { t } from '../../i18n/t';
import { AuthCard } from './AuthCard';

export default function SetupPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: '', display_name: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await api.setup(form);
      await signIn(form.email, form.password, false);
      navigate('/');
    } catch (err) {
      setError(errorText(err, t('setup.failed')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <BareShell>
      <AuthCard title={t('setup.title')} intro={t('setup.intro')} width={460}>
        {error && <Alert severity="error">{error}</Alert>}
        <Stack component="form" spacing={2} onSubmit={submit} noValidate>
          <TextField id="setup-name" label={t('setup.name')} value={form.display_name} onChange={set('display_name')} required />
          <TextField id="setup-email" label={t('setup.email')} type="email" value={form.email} onChange={set('email')} required />
          <TextField id="setup-password" label={t('setup.password')} type="password" autoComplete="new-password"
            value={form.password} onChange={set('password')} required />
          <Button type="submit" variant="contained" disabled={busy || form.password.length < 10}>{t('setup.submit')}</Button>
        </Stack>
      </AuthCard>
    </BareShell>
  );
}
