import React from 'react';
import { Platform, StyleSheet } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { colors, typography } from '../theme';
import WorkbenchStack from './WorkbenchStack';
import PondsStack from './PondsStack';
import FeedingStack from './FeedingStack';
import WarehouseStack from './WarehouseStack';
import MoreStack from './MoreStack';

export type MainTabParamList = {
  WorkbenchTab: undefined;
  PondsTab: undefined;
  FeedingTab: undefined;
  WarehouseTab: undefined;
  MoreTab: undefined;
};

const Tab = createBottomTabNavigator<MainTabParamList>();

const getTabIcon = (routeName: string, focused: boolean): keyof typeof Ionicons.glyphMap => {
  const icons: Record<string, { active: keyof typeof Ionicons.glyphMap; inactive: keyof typeof Ionicons.glyphMap }> = {
    WorkbenchTab: { active: 'home', inactive: 'home-outline' },
    PondsTab: { active: 'water', inactive: 'water-outline' },
    FeedingTab: { active: 'nutrition', inactive: 'nutrition-outline' },
    WarehouseTab: { active: 'cube', inactive: 'cube-outline' },
    MoreTab: { active: 'ellipsis-horizontal', inactive: 'ellipsis-horizontal-outline' },
  };
  const icon = icons[routeName];
  return focused ? icon.active : icon.inactive;
};

export const MainTabs: React.FC = () => {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarIcon: ({ focused, color, size }) => {
          const iconName = getTabIcon(route.name, focused);
          return <Ionicons name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.gray2,
        tabBarStyle: styles.tabBar,
        tabBarLabelStyle: styles.tabBarLabel,
        tabBarItemStyle: styles.tabBarItem,
      })}
    >
      <Tab.Screen
        name="WorkbenchTab"
        component={WorkbenchStack}
        options={{ tabBarLabel: '工作台' }}
      />
      <Tab.Screen
        name="PondsTab"
        component={PondsStack}
        options={{ tabBarLabel: '塘口' }}
      />
      <Tab.Screen
        name="FeedingTab"
        component={FeedingStack}
        options={{ tabBarLabel: '投喂' }}
      />
      <Tab.Screen
        name="WarehouseTab"
        component={WarehouseStack}
        options={{ tabBarLabel: '仓储' }}
      />
      <Tab.Screen
        name="MoreTab"
        component={MoreStack}
        options={{ tabBarLabel: '更多' }}
      />
    </Tab.Navigator>
  );
};

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: colors.background,
    borderTopColor: colors.separatorLight,
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: 8,
    paddingBottom: Platform.OS === 'ios' ? 24 : 8,
    height: Platform.OS === 'ios' ? 88 : 64,
  },
  tabBarLabel: {
    ...typography.caption2,
    fontWeight: '500',
  },
  tabBarItem: {
    paddingVertical: 4,
  },
});

export default MainTabs;
