import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormHelperText, InputLabel,
  MenuItem, Select, Stack, TextField } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { keys } from '../../app/links';
import { t } from '../../i18n/t';

const FIELDS = ['program_code', 'program_name', 'client_id', 'description'];

// Slice 1f §3.7 (function 134): a platform admin edits the program header. Only changed fields are sent; the server
// upper-cases the code, refuses a client change while any project is in the program and audits what changed.
export default function ProgramEditDialog({ program, projectCount, onClose, onSaved }) {
  const qc = useQueryClient();
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients });
  const [f, setF] = useState(() => ({ ...program, description: program.description ?? '' }));
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const changed = Object.fromEntries(FIELDS.filter((k) => f[k] !== (k === 'description' ? program.description ?? '' : program[k]))
    .map((k) => [k, k === 'description' && f[k].trim() === '' ? null : f[k]]));
  const save = useMutation({
    mutationFn: () => api.updateProgram(program.program_id, { row_version: program.row_version, ...changed }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.program(program.program_id) });
      qc.invalidateQueries({ queryKey: ['programs'] });
      qc.invalidateQueries({ queryKey: ['projects'] });          // project screens show the program code (sara L3)
      qc.invalidateQueries({ queryKey: ['project'] });
      onSaved();
    },
  });
  const live = clients.data ?? [];
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('program.edit.title')}</DialogTitle>
      <DialogContent>
        {save.error && <Alert severity="error" sx={{ mb: 2 }}>{errorText(save.error, t('common.saveFailed'))}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="pe-code" label={t('admin.programCode')} value={f.program_code} onChange={set('program_code')}
            slotProps={{ htmlInput: { maxLength: 30 } }} />
          <TextField id="pe-name" label={t('admin.programName')} value={f.program_name} onChange={set('program_name')}
            slotProps={{ htmlInput: { maxLength: 200 } }} />
          <FormControl disabled={projectCount > 0}>
            <InputLabel id="pe-client-label">{t('admin.client')}</InputLabel>
            <Select labelId="pe-client-label" id="pe-client" label={t('admin.client')}
              value={live.some((c) => c.client_id === f.client_id) ? f.client_id : ''} onChange={set('client_id')}>
              {live.map((c) => <MenuItem key={c.client_id} value={c.client_id}>{c.client_name}</MenuItem>)}
            </Select>
            {projectCount > 0 && <FormHelperText>{t('program.edit.clientLocked')}</FormHelperText>}
          </FormControl>
          <TextField id="pe-desc" label={t('program.edit.description')} value={f.description} onChange={set('description')}
            multiline minRows={2} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={save.isPending || Object.keys(changed).length === 0}
          onClick={() => save.mutate()}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}
