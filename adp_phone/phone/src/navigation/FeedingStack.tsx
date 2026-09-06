import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import FeedPlanScreen from '../screens/feeding/FeedPlanScreen';
import FeedPlanCreateScreen from '../screens/feeding/FeedPlanCreateScreen';
import FeedTaskScreen from '../screens/feeding/FeedTaskScreen';
import FeedLogScreen from '../screens/feeding/FeedLogScreen';
import FeedLogCreateScreen from '../screens/feeding/FeedLogCreateScreen';
import DailyOpsScreen from '../screens/production/DailyOpsScreen';
import DailyOpsCreateScreen from '../screens/production/DailyOpsCreateScreen';

export type FeedingStackParamList = {
  FeedPlanList: undefined;
  FeedPlanCreate: undefined;
  FeedTasks: undefined;
  FeedLog: undefined;
  FeedLogCreate: undefined;
  DailyOps: undefined;
  DailyOpsCreate: undefined;
};

const Stack = createNativeStackNavigator<FeedingStackParamList>();

export const FeedingStack: React.FC = () => {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="FeedPlanList" component={FeedPlanScreen} />
      <Stack.Screen name="FeedPlanCreate" component={FeedPlanCreateScreen} options={{ animation: 'slide_from_bottom' }} />
      <Stack.Screen name="FeedTasks" component={FeedTaskScreen} />
      <Stack.Screen name="FeedLog" component={FeedLogScreen} />
      <Stack.Screen name="FeedLogCreate" component={FeedLogCreateScreen} options={{ animation: 'slide_from_bottom' }} />
      <Stack.Screen name="DailyOps" component={DailyOpsScreen} />
      <Stack.Screen name="DailyOpsCreate" component={DailyOpsCreateScreen} options={{ animation: 'slide_from_bottom' }} />
    </Stack.Navigator>
  );
};

export default FeedingStack;
