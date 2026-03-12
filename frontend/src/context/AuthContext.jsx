import React, { createContext, useContext, useState, useEffect } from 'react';
import { fetchMe } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState({
    user: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    fetchMe()
      .then((user) => setAuth({ user, loading: false, error: null }))
      .catch((err) => setAuth({ user: null, loading: false, error: err.message }));
  }, []);

  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
