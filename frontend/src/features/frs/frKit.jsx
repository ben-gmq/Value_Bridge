import { Alert, Stack } from '@mui/material';
import { t } from '../../i18n/t';

// Shared pieces of the FR screens (Slice 6a).

// The live solutions an FR may sit under, as select options; '' means none (D-28).
export const solutionOptions = (solutions) => (solutions ?? []).filter((s) => s.is_active)
  .map((s) => ({ value: s.solution_id, label: `${s.solution_number} ${s.solution_name}` }));

// What the server said about the save — never errors (D-28, DR6a-P2, S6a-5).
export function FrWarnings({ warnings, onClose }) {
  if (!warnings?.length) return null;
  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {warnings.map((w) => (
        <Alert key={w} severity="warning" onClose={onClose}>{t(`frs.warn.${w}`)}</Alert>
      ))}
    </Stack>
  );
}
