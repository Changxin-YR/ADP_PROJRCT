import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import WarehouseHomeScreen from '../screens/warehouse/WarehouseHomeScreen';
import ReceiptListScreen from '../screens/warehouse/ReceiptListScreen';
import IssueListScreen from '../screens/warehouse/IssueListScreen';
import StocktakeScreen from '../screens/warehouse/StocktakeScreen';
import StockAlertsScreen from '../screens/warehouse/StockAlertsScreen';
import StockInOutScreen from '../screens/warehouse/StockInOutScreen';
import MaterialsScreen from '../screens/warehouse/MaterialsScreen';
import WarehouseTransfersScreen from '../screens/warehouse/WarehouseTransfersScreen';
import WarehouseReturnsScreen from '../screens/warehouse/WarehouseReturnsScreen';
import ScrapsScreen from '../screens/warehouse/ScrapsScreen';

export type WarehouseStackParamList = {
  WarehouseHome: undefined;
  ReceiptList: undefined;
  IssueList: undefined;
  Stocktake: undefined;
  StockAlerts: undefined;
  StockInOut: { materialId?: string };
  Materials: undefined;
  WarehouseTransfers: undefined;
  WarehouseReturns: undefined;
  Scraps: undefined;
};

const Stack = createNativeStackNavigator<WarehouseStackParamList>();

export const WarehouseStack: React.FC = () => {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="WarehouseHome" component={WarehouseHomeScreen} />
      <Stack.Screen name="ReceiptList" component={ReceiptListScreen} />
      <Stack.Screen name="IssueList" component={IssueListScreen} />
      <Stack.Screen name="Stocktake" component={StocktakeScreen} />
      <Stack.Screen name="StockAlerts" component={StockAlertsScreen} />
      <Stack.Screen name="StockInOut" component={StockInOutScreen} />
      <Stack.Screen name="Materials" component={MaterialsScreen} />
      <Stack.Screen name="WarehouseTransfers" component={WarehouseTransfersScreen} />
      <Stack.Screen name="WarehouseReturns" component={WarehouseReturnsScreen} />
      <Stack.Screen name="Scraps" component={ScrapsScreen} />
    </Stack.Navigator>
  );
};

export default WarehouseStack;
