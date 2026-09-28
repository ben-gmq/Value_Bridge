import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Card, CardContent, Checkbox, FormControlLabel, Stack, TextField, Typography } from '@mui/material';
import { StorageBlockedError, useAuth } from '../../app/AuthContext';
import { errorText } from '../../api/client';
import { BareShell } from '../../components/AppShell';
import { t } from '../../i18n/t';

export default function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await signIn(email, password, remember);
      navigate('/');
    } catch (err) {
      setError(err instanceof StorageBlockedError ? t('login.storageBlocked') : errorText(err, t('login.failed')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <BareShell>
      <Card sx={{ width: 400, maxWidth: '100%' }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={1} sx={{ alignItems: 'center', mb: 3 }}>
            <Box sx={(th) => ({ width: 40, height: 40, borderRadius: '20px', bgcolor: th.vars.palette.brand.ftc,
              color: th.vars.palette.brand.onFtc, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 })}>VB</Box>
            <Typography variant="h5" component="h1" sx={(th) => ({ color: th.vars.palette.brand.title })}>{t('login.title')}</Typography>
          </Stack>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <Box component="form" onSubmit={submit} noValidate>
            <Stack spacing={2}>
              <TextField id="login-email" label={t('login.email')} type="email" autoComplete="username"
                value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
              <TextField id="login-password" label={t('login.password')} type="password" autoComplete="current-password"
                value={password} onChange={(e) => setPassword(e.target.value)} required />
              <FormControlLabel control={<Checkbox id="login-remember" checked={remember} onChange={(e) => setRemember(e.target.checked)} />}
                label={t('login.remember')} />
              <Button type="submit" variant="contained" size="large" disabled={busy || !email || !password}>{t('login.submit')}</Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>
    </BareShell>
  );
}
