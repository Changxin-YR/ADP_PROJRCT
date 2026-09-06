import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RouteProp } from '@react-navigation/native';
import { AuthStackParamList } from './AuthStack';
import { WorkbenchStackParamList } from './WorkbenchStack';
import { PondsStackParamList } from './PondsStack';
import { FeedingStackParamList } from './FeedingStack';
import { WarehouseStackParamList } from './WarehouseStack';
import { MoreStackParamList } from './MoreStack';
import { MainTabParamList } from './MainTabs';

export type {
  AuthStackParamList,
  WorkbenchStackParamList,
  PondsStackParamList,
  FeedingStackParamList,
  WarehouseStackParamList,
  MoreStackParamList,
  MainTabParamList,
};

// Helper types for navigation props
export type AuthNavProp<T extends keyof AuthStackParamList> = NativeStackNavigationProp<AuthStackParamList, T>;
export type AuthRouteProp<T extends keyof AuthStackParamList> = RouteProp<AuthStackParamList, T>;

export type PondsNavProp<T extends keyof PondsStackParamList> = NativeStackNavigationProp<PondsStackParamList, T>;
export type PondsRouteProp<T extends keyof PondsStackParamList> = RouteProp<PondsStackParamList, T>;
