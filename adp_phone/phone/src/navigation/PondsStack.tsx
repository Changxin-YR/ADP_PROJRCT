import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import PondListScreen from '../screens/ponds/PondListScreen';
import PondDetailScreen from '../screens/ponds/PondDetailScreen';
import PondCreateScreen from '../screens/ponds/PondCreateScreen';
import BatchesScreen from '../screens/production/BatchesScreen';
import BatchCreateScreen from '../screens/production/BatchCreateScreen';
import SamplingScreen from '../screens/production/SamplingScreen';

export type PondsStackParamList = {
  PondList: undefined;
  PondDetail: { pondId: string };
  PondCreate: undefined;
  Batches: undefined;
  BatchCreate: undefined;
  Sampling: undefined;
};

const Stack = createNativeStackNavigator<PondsStackParamList>();

export const PondsStack: React.FC = () => {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="PondList" component={PondListScreen} />
      <Stack.Screen name="PondDetail" component={PondDetailScreen} />
      <Stack.Screen name="PondCreate" component={PondCreateScreen} />
      <Stack.Screen name="Batches" component={BatchesScreen} />
      <Stack.Screen name="BatchCreate" component={BatchCreateScreen} options={{ animation: 'slide_from_bottom' }} />
      <Stack.Screen name="Sampling" component={SamplingScreen} />
    </Stack.Navigator>
  );
};

export default PondsStack;
