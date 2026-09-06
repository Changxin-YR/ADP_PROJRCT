import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  FlatList,
  RefreshControl,
  Dimensions,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Card } from '../../components';
import { Badge } from '../../components/common/Badge';
import { warehouseApi } from '../../api/warehouse';
import { masterDataApi } from '../../api/masterData';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

type WarehouseHomeScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

interface RecentActivity {
  id: string;
  type: 'in' | 'out';
  materialName: string;
  quantity: number;
  unit: string;
  date: string;
  operator: string;
}

const WarehouseHomeScreen: React.FC<WarehouseHomeScreenProps> = ({ navigation }) => {
  const [refreshing, setRefreshing] = useState(false);
  const [activities] = useState<RecentActivity[]>([]);
  const [stats, setStats] = useState({ materialCount: 0, lowStock: 0, monthIn: 0, monthOut: 0 });

  const fetchStats = useCallback(async () => {
    try {
      const [materialsData, alertsData] = await Promise.all([
        masterDataApi.listMaterials(1, 1),
        warehouseApi.listAlerts(),
      ]);
      setStats({
        materialCount: materialsData.total || 0,
        lowStock: alertsData.filter((a: any) => a.alert_type === 'low_stock').length,
        monthIn: 0,
        monthOut: 0,
      });
    } catch (err) {
      console.warn('Failed to load warehouse stats', err);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchStats().finally(() => setRefreshing(false));
  }, [fetchStats]);

  const quickActions = [
    { icon: 'enter-outline' as const, label: '入库', color: '#34C759', route: 'ReceiptList' },
    { icon: 'exit-outline' as const, label: '出库', color: '#FF9500', route: 'IssueList' },
    { icon: 'clipboard-outline' as const, label: '盘点', color: '#007AFF', route: 'Stocktake' },
    { icon: 'alert-circle-outline' as const, label: '库存预警', color: '#FF3B30', route: 'StockAlerts' },
    { icon: 'swap-horizontal-outline' as const, label: '调拨', color: '#AF52DE', route: 'WarehouseTransfers' },
    { icon: 'return-down-back-outline' as const, label: '退库', color: '#5AC8FA', route: 'WarehouseReturns' },
    { icon: 'trash-outline' as const, label: '报损报废', color: '#8E8E93', route: 'Scraps' },
    { icon: 'cube-outline' as const, label: '物料档案', color: '#007AFF', route: 'Materials' },
  ];

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>仓储管理</Text>
        </View>

        {/* Quick Actions */}
        <Card style={styles.actionsCard}>
          <View style={styles.actionsGrid}>
            {quickActions.map((action, index) => (
              <TouchableOpacity
                key={index}
                style={styles.actionItem}
                onPress={() => navigation.navigate(action.route)}
                activeOpacity={0.7}
              >
                <View style={[styles.actionIcon, { backgroundColor: action.color + '15' }]}>
                  <Ionicons name={action.icon} size={24} color={action.color} />
                </View>
                <Text style={styles.actionLabel}>{action.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </Card>

        {/* Stock Overview */}
        <Card title="库存概览" style={styles.section}>
          <View style={styles.stockGrid}>
            <View style={styles.stockItem}>
              <Text style={styles.stockValue}>{stats.materialCount}</Text>
              <Text style={styles.stockLabel}>物料种类</Text>
            </View>
            <View style={styles.stockItem}>
              <Text style={[styles.stockValue, stats.lowStock > 0 && { color: colors.error }]}>{stats.lowStock}</Text>
              <Text style={styles.stockLabel}>低库存项</Text>
            </View>
            <View style={styles.stockItem}>
              <Text style={styles.stockValue}>{stats.monthIn}</Text>
              <Text style={styles.stockLabel}>本月入库</Text>
            </View>
            <View style={styles.stockItem}>
              <Text style={styles.stockValue}>{stats.monthOut}</Text>
              <Text style={styles.stockLabel}>本月出库</Text>
            </View>
          </View>
        </Card>

        {/* Recent Activity */}
        <Card title="最近动态" style={styles.section}>
          {activities.length === 0 ? (
            <View style={styles.emptyContainer}>
              <Ionicons name="cube-outline" size={40} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无出入库记录</Text>
            </View>
          ) : (
            activities.map((item, index) => (
              <Animated.View key={item.id} entering={FadeInDown.delay(index * 50).duration(300)}>
                <View style={styles.activityItem}>
                  <View style={[
                    styles.activityBadge,
                    { backgroundColor: item.type === 'in' ? '#34C759' + '20' : '#FF9500' + '20' },
                  ]}>
                    <Ionicons
                      name={item.type === 'in' ? 'enter-outline' : 'exit-outline'}
                      size={16}
                      color={item.type === 'in' ? '#34C759' : '#FF9500'}
                    />
                  </View>
                  <View style={styles.activityContent}>
                    <Text style={styles.activityName}>{item.materialName}</Text>
                    <Text style={styles.activityMeta}>
                      {item.type === 'in' ? '入库' : '出库'} {item.quantity}{item.unit} · {item.operator}
                    </Text>
                  </View>
                  <Text style={styles.activityDate}>{item.date}</Text>
                </View>
              </Animated.View>
            ))
          )}
        </Card>
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
    maxWidth: isTablet ? layout.maxContentWidth : undefined,
    alignSelf: isTablet ? 'center' : undefined,
    width: '100%',
  },
  header: {
    marginBottom: spacing.lg,
  },
  title: {
    ...typography.largeTitle,
    color: colors.text,
  },
  actionsCard: {
    marginBottom: spacing.lg,
  },
  actionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'flex-start',
    paddingVertical: spacing.md,
    gap: spacing.md,
  },
  actionItem: {
    alignItems: 'center',
    width: '22%',
    gap: spacing.sm,
  },
  actionIcon: {
    width: 48,
    height: 48,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  actionLabel: {
    ...typography.caption1,
    color: colors.text,
    fontWeight: '500',
  },
  section: {
    marginBottom: spacing.lg,
  },
  stockGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: spacing.md,
  },
  stockItem: {
    width: '50%',
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  stockValue: {
    ...typography.title2,
    color: colors.text,
  },
  stockLabel: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 4,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: spacing.xl,
  },
  emptyText: {
    ...typography.body,
    color: colors.textTertiary,
    marginTop: spacing.md,
  },
  activityItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  activityBadge: {
    width: 32,
    height: 32,
    borderRadius: borderRadius.sm,
    justifyContent: 'center',
    alignItems: 'center',
  },
  activityContent: {
    flex: 1,
    marginLeft: spacing.md,
  },
  activityName: {
    ...typography.body,
    color: colors.text,
    fontWeight: '500',
  },
  activityMeta: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  activityDate: {
    ...typography.caption2,
    color: colors.gray3,
  },
});

export default WarehouseHomeScreen;
