import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import WorkbenchScreen from '../screens/workbench/WorkbenchScreen';
import NotificationsScreen from '../screens/workbench/NotificationsScreen';

export type WorkbenchStackParamList = {
  WorkbenchHome: undefined;
  Notifications: undefined;
};

const Stack = createNativeStackNavigator<WorkbenchStackParamList>();

export const WorkbenchStack: React.FC = () => {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="WorkbenchHome" component={WorkbenchScreen} />
      <Stack.Screen name="Notifications" component={NotificationsScreen} />
    </Stack.Navigator>
  );
};

export default WorkbenchStack;
