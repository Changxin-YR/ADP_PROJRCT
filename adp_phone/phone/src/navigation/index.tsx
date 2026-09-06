import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { useAuth } from '../hooks/useAuth';
import { Loading } from '../components';
import AuthStack from './AuthStack';
import MainTabs from './MainTabs';
import PendingScreen from '../screens/auth/PendingScreen';
import PasswordChangeScreen from '../screens/auth/PasswordChangeScreen';

export const RootNavigation: React.FC = () => {
  const { isAuthenticated, isLoading, user } = useAuth();

  if (isLoading) {
    return <Loading fullScreen message="Loading..." />;
  }

  return (
    <NavigationContainer>
      {user?.status === 'pending' || user?.status === 'rejected' ? <PendingScreen /> : user?.status === 'must_change_password' ? <PasswordChangeScreen navigation={{ goBack: () => undefined } as any} /> : isAuthenticated ? <MainTabs /> : <AuthStack />}
    </NavigationContainer>
  );
};

export default RootNavigation;
