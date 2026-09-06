import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import MoreScreen from '../screens/more/MoreScreen';
import PurchaseScreen from '../screens/more/PurchaseScreen';
import SalesScreen from '../screens/more/SalesScreen';
import CostScreen from '../screens/more/CostScreen';
import DataExchangeScreen from '../screens/more/DataExchangeScreen';
import ProfileScreen from '../screens/more/ProfileScreen';
import PasswordChangeScreen from '../screens/auth/PasswordChangeScreen';
import BatchesScreen from '../screens/production/BatchesScreen';
import DailyOpsScreen from '../screens/production/DailyOpsScreen';
import SamplingScreen from '../screens/production/SamplingScreen';
import TransfersScreen from '../screens/production/TransfersScreen';
import LossesScreen from '../screens/production/LossesScreen';
import HarvestsScreen from '../screens/production/HarvestsScreen';
import SupplierScreen from '../screens/more/SupplierScreen';
import CustomerScreen from '../screens/more/CustomerScreen';

export type MoreStackParamList = {
  MoreHome: undefined;
  Purchase: undefined;
  Sales: undefined;
  Cost: undefined;
  DataExchange: undefined;
  Profile: undefined;
  ChangePassword: undefined;
  Batches: undefined;
  DailyOps: undefined;
  Sampling: undefined;
  Transfers: undefined;
  Losses: undefined;
  Harvests: undefined;
  Suppliers: undefined;
  Customers: undefined;
};

const Stack = createNativeStackNavigator<MoreStackParamList>();

export const MoreStack: React.FC = () => {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="MoreHome" component={MoreScreen} />
      <Stack.Screen name="Purchase" component={PurchaseScreen} />
      <Stack.Screen name="Sales" component={SalesScreen} />
      <Stack.Screen name="Cost" component={CostScreen} />
      <Stack.Screen name="DataExchange" component={DataExchangeScreen} />
      <Stack.Screen name="Profile" component={ProfileScreen} />
      <Stack.Screen name="ChangePassword" component={PasswordChangeScreen} />
      <Stack.Screen name="Batches" component={BatchesScreen} />
      <Stack.Screen name="DailyOps" component={DailyOpsScreen} />
      <Stack.Screen name="Sampling" component={SamplingScreen} />
      <Stack.Screen name="Transfers" component={TransfersScreen} />
      <Stack.Screen name="Losses" component={LossesScreen} />
      <Stack.Screen name="Harvests" component={HarvestsScreen} />
      <Stack.Screen name="Suppliers" component={SupplierScreen} />
      <Stack.Screen name="Customers" component={CustomerScreen} />
    </Stack.Navigator>
  );
};

export default MoreStack;
