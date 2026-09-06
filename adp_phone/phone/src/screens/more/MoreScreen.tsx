import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../hooks/useAuth';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

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

type MoreScreenProps = {
  navigation: NativeStackNavigationProp<MoreStackParamList, 'MoreHome'>;
};

interface MenuSection {
  title: string;
  items: MenuItem[];
}

interface MenuItem {
  icon: keyof typeof Ionicons.glyphMap;
  iconColor: string;
  label: string;
  route?: keyof MoreStackParamList;
  onPress?: () => void;
}

const MoreScreen: React.FC<MoreScreenProps> = ({ navigation }) => {
  const { user, logout } = useAuth();

  const handleLogout = () => {
    Alert.alert(
      '退出登录',
      '确定要退出登录吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确认退出',
          style: 'destructive',
          onPress: async () => {
            await logout();
          },
        },
      ]
    );
  };

  const sections: MenuSection[] = [
    {
      title: '养殖生产',
      items: [
        { icon: 'fish-outline', iconColor: '#34C759', label: '养殖批次', route: 'Batches' },
        { icon: 'clipboard-outline', iconColor: '#007AFF', label: '日常操作', route: 'DailyOps' },
        { icon: 'analytics-outline', iconColor: '#5AC8FA', label: '抽样检测', route: 'Sampling' },
        { icon: 'swap-horizontal-outline', iconColor: '#AF52DE', label: '转塘记录', route: 'Transfers' },
        { icon: 'trending-down-outline', iconColor: '#FF3B30', label: '损耗记录', route: 'Losses' },
        { icon: 'basket-outline', iconColor: '#FF9500', label: '出塘记录', route: 'Harvests' },
      ],
    },
    {
      title: '业务管理',
      items: [
        { icon: 'cart-outline', iconColor: '#007AFF', label: '采购管理', route: 'Purchase' },
        { icon: 'cash-outline', iconColor: '#34C759', label: '销售管理', route: 'Sales' },
        { icon: 'calculator-outline', iconColor: '#FF9500', label: '成本核算', route: 'Cost' },
        { icon: 'business-outline', iconColor: '#5AC8FA', label: '供应商档案', route: 'Suppliers' },
        { icon: 'people-outline', iconColor: '#AF52DE', label: '客户档案', route: 'Customers' },
      ],
    },
    {
      title: '工具',
      items: [
        { icon: 'swap-horizontal-outline', iconColor: '#5AC8FA', label: '数据导入导出', route: 'DataExchange' },
      ],
    },
    {
      title: '账户',
      items: [
        { icon: 'person-outline', iconColor: '#AF52DE', label: '个人信息', route: 'Profile' },
        { icon: 'lock-closed-outline', iconColor: '#8E8E93', label: '修改密码', route: 'ChangePassword' },
        { icon: 'log-out-outline', iconColor: '#FF3B30', label: '退出登录', onPress: handleLogout },
      ],
    },
  ];

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>更多</Text>
        </View>

        {/* User Card */}
        <TouchableOpacity
          style={styles.userCard}
          onPress={() => navigation.navigate('Profile')}
          activeOpacity={0.7}
        >
          <View style={styles.avatar}>
            <Ionicons name="person" size={28} color={colors.primary} />
          </View>
          <View style={styles.userInfo}>
            <Text style={styles.userName}>{user?.name || user?.login_name || '用户'}</Text>
            <Text style={styles.userRole}>{user?.roles?.[0]?.name || '操作员'}</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.gray3} />
        </TouchableOpacity>

        {/* Menu Sections */}
        {sections.map((section, sIndex) => (
          <View key={sIndex} style={styles.section}>
            <Text style={styles.sectionTitle}>{section.title}</Text>
            <View style={styles.sectionCard}>
              {section.items.map((item, iIndex) => (
                <TouchableOpacity
                  key={iIndex}
                  style={[
                    styles.menuItem,
                    iIndex < section.items.length - 1 && styles.menuItemBorder,
                  ]}
                  onPress={() => {
                    if (item.onPress) {
                      item.onPress();
                    } else if (item.route) {
                      navigation.navigate(item.route);
                    }
                  }}
                  activeOpacity={0.6}
                >
                  <View style={[styles.menuIcon, { backgroundColor: item.iconColor + '15' }]}>
                    <Ionicons name={item.icon} size={20} color={item.iconColor} />
                  </View>
                  <Text style={styles.menuLabel}>{item.label}</Text>
                  {!item.onPress && (
                    <Ionicons name="chevron-forward" size={18} color={colors.gray3} />
                  )}
                </TouchableOpacity>
              ))}
            </View>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundSecondary,
  },
  scrollContent: {
    padding: layout.screenPadding,
  },
  header: {
    marginBottom: spacing.lg,
  },
  title: {
    ...typography.largeTitle,
    color: colors.text,
  },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    marginBottom: spacing.xl,
    ...shadows.sm,
  },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  userInfo: {
    flex: 1,
    marginLeft: spacing.md,
  },
  userName: {
    ...typography.headline,
    color: colors.text,
  },
  userRole: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  section: {
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    ...typography.caption1,
    color: colors.textTertiary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
    marginLeft: spacing.xs,
  },
  sectionCard: {
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    ...shadows.sm,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.base,
  },
  menuItemBorder: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  menuIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  menuLabel: {
    ...typography.body,
    color: colors.text,
    flex: 1,
  },
});

export default MoreScreen;
