import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import BatchesScreen from '../screens/production/BatchesScreen';
import DailyOpsScreen from '../screens/production/DailyOpsScreen';
import SamplingScreen from '../screens/production/SamplingScreen';

export type ProductionStackParamList = {
  Batches: undefined;
  DailyOps: undefined;
  Sampling: undefined;
};

const Stack = createNativeStackNavigator<ProductionStackParamList>();

export const ProductionStack: React.FC = () => {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="Batches" component={BatchesScreen} />
      <Stack.Screen name="DailyOps" component={DailyOpsScreen} />
      <Stack.Screen name="Sampling" component={SamplingScreen} />
    </Stack.Navigator>
  );
};

export default ProductionStack;
