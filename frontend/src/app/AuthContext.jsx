import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/vb';
import { tokenStore } from '../api/client';

const AuthContext = createContext(null);

export class StorageBlockedError extends Error {}

export function AuthProvider({ children }) {
  const qc = useQueryClient();
  // The token lives in React state, not only in localStorage: a sign-in must re-render the
  // tree so the route guards see it (Gate 2 UAT — sign-in used to stay on /login).
  const [token, setToken] = useState(() => tokenStore.get());
  const me = useQuery({ queryKey: ['me', token], queryFn: api.me, enabled: Boolean(token), retry: false });

  const signIn = useCallback(async (email, password, rememberMe) => {
    const res = await api.login({ email, password, remember_me: rememberMe });
    if (!tokenStore.set(res.access_token)) throw new StorageBlockedError();
    qc.clear();
    await qc.fetchQuery({ queryKey: ['me', res.access_token], queryFn: api.me });
    setToken(res.access_token);
  }, [qc]);

  const signOut = useCallback(() => {
    tokenStore.clear();
    qc.clear();
    setToken(null);
    window.location.assign('/login');
  }, [qc]);

  const value = useMemo(() => ({
    me: me.data, loading: Boolean(token) && me.isLoading, signedIn: Boolean(token) && Boolean(me.data),
    isAdmin: Boolean(me.data?.user?.is_platform_admin), signIn, signOut,
  }), [me.data, me.isLoading, token, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
