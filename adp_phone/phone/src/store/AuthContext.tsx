import React, { createContext, useState, useEffect, ReactNode } from 'react';
import { RegistrationRequest, RegistrationResult, User } from '../types';
import { authApi } from '../api/auth';
import { apiClient } from '../api/client';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthContextType extends AuthState {
  login: (identifier: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  register: (data: RegistrationRequest) => Promise<RegistrationResult>;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [state, setState] = useState<AuthState>({
    user: null,
    isAuthenticated: false,
    isLoading: true,
  });

  useEffect(() => {
    checkAuth();
  }, []);

  const canEnterBusiness = (user: User) => user.status === 'active';

  const checkAuth = async () => {
    try {
      const hasSession = await apiClient.hasSession();
      if (hasSession) {
        const user = await authApi.getMe();
        setState({ user, isAuthenticated: canEnterBusiness(user), isLoading: false });
      } else {
        setState({ user: null, isAuthenticated: false, isLoading: false });
      }
    } catch {
      setState({ user: null, isAuthenticated: false, isLoading: false });
    }
  };

  const login = async (identifier: string, password: string): Promise<User> => {
    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const user = await authApi.login({ identifier, password });
      setState({
        user,
        isAuthenticated: canEnterBusiness(user),
        isLoading: false,
      });
      return user;
    } catch (error) {
      setState((prev) => ({ ...prev, isLoading: false }));
      throw error;
    }
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      setState({ user: null, isAuthenticated: false, isLoading: false });
    }
  };

  const refreshUser = async () => {
    try {
      const user = await authApi.getMe();
      setState((prev) => ({ ...prev, user, isAuthenticated: canEnterBusiness(user) }));
    } catch {
      // Silently fail
    }
  };

  const register = async (data: RegistrationRequest): Promise<RegistrationResult> => {
    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const result = await authApi.register(data);
      let user: User;
      try {
        user = await authApi.getMe();
      } catch {
        user = result.user as User;
      }
      setState({ user, isAuthenticated: canEnterBusiness(user), isLoading: false });
      return result;
    } catch (error) {
      setState((prev) => ({ ...prev, isLoading: false }));
      throw error;
    }
  };

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        logout,
        refreshUser,
        register,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export default AuthProvider;
