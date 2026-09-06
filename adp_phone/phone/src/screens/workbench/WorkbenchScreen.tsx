import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Dimensions,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Card } from '../../components';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';
import { WorkbenchStackParamList } from '../../navigation/WorkbenchStack';
import { useAuth } from '../../hooks/useAuth';
import { workbenchApi } from '../../api/workbench';
import { WorkbenchSummary, WorkItem } from '../../types';

type WorkbenchScreenProps = {
  navigation: NativeStackNavigationProp<WorkbenchStackParamList, 'WorkbenchHome'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

interface StatCardProps {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
  color: string;
}

const StatCard: React.FC<StatCardProps> = ({ icon, label, value, color }) => (
  <View style={styles.statCard}>
    <View style={[styles.statIconContainer, { backgroundColor: color + '15' }]}>
      <Ionicons name={icon} size={22} color={color} />
    </View>
    <Text style={styles.statValue}>{value}</Text>
    <Text style={styles.statLabel}>{label}</Text>
  </View>
);

const getGreeting = (): string => {
  const hour = new Date().getHours();
  if (hour < 6) return '凌晨好';
  if (hour < 12) return '上午好';
  if (hour < 14) return '中午好';
  if (hour < 18) return '下午好';
  return '晚上好';
};

const WorkbenchScreen: React.FC<WorkbenchScreenProps> = ({ navigation }) => {
  const { user } = useAuth();
  const [summary, setSummary] = useState<WorkbenchSummary | null>(null);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      const [summaryData, workData] = await Promise.all([
        workbenchApi.getSummary().catch(() => null),
        workbenchApi.listWorkItems(1, 'pending').catch(() => ({ items: [], total: 0 })),
      ]);
      if (summaryData) setSummary(summaryData);
      setWorkItems(workData.items.slice(0, 5));
    } catch (err) {
      console.warn('Failed to load workbench data', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const userName = user?.name || user?.login_name || '用户';

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => fetchData(true)} tintColor={colors.primary} />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>{getGreeting()}，{userName}</Text>
            <Text style={styles.title}>工作台</Text>
          </View>
          <TouchableOpacity
            style={styles.notificationButton}
            onPress={() => navigation.navigate('Notifications')}
          >
            <Ionicons name="notifications-outline" size={24} color={colors.text} />
            {(summary as any)?.unread_notifications > 0 && <View style={styles.notificationBadge} />}
          </TouchableOpacity>
        </View>

        {/* Stats Grid */}
        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: spacing.xl }} />
        ) : (
          <View style={styles.statsGrid}>
            <StatCard
              icon="water"
              label="活跃塘口"
              value={String(summary?.kpis?.active_ponds ?? 0)}
              color={colors.primary}
            />
            <StatCard
              icon="fish"
              label="在养批次"
              value={String(summary?.kpis?.active_batches ?? 0)}
              color={colors.success}
            />
            <StatCard
              icon="nutrition"
              label="今日投喂(kg)"
              value={String(summary?.kpis?.today_feed_kg ?? 0)}
              color={colors.warning}
            />
            <StatCard
              icon="alert-circle"
              label="待处理告警"
              value={String(summary?.kpis?.pending_alerts ?? 0)}
              color={colors.error}
            />
          </View>
        )}

        {/* Quick Actions */}
        <Card title="快捷操作" style={styles.section}>
          <View style={styles.quickActions}>
            {[
              { icon: 'nutrition-outline' as const, label: '投喂记录', color: '#FF9500', onPress: () => navigation.getParent()?.navigate('FeedingTab') },
              { icon: 'clipboard-outline' as const, label: '巡塘记录', color: '#007AFF', onPress: () => {} },
              { icon: 'enter-outline' as const, label: '入库', color: '#34C759', onPress: () => navigation.getParent()?.navigate('WarehouseTab') },
              { icon: 'exit-outline' as const, label: '出库', color: '#AF52DE', onPress: () => navigation.getParent()?.navigate('WarehouseTab') },
            ].map((action, index) => (
              <TouchableOpacity key={index} style={styles.quickActionItem} onPress={action.onPress} activeOpacity={0.7}>
                <View style={[styles.quickActionIcon, { backgroundColor: action.color + '15' }]}>
                  <Ionicons name={action.icon} size={24} color={action.color} />
                </View>
                <Text style={styles.quickActionLabel}>{action.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </Card>

        {/* Today's Tasks */}
        <Card title="待办事项" subtitle={`${workItems.length} 项待处理`} style={styles.section}>
          <View style={styles.taskList}>
            {workItems.length === 0 ? (
              <Text style={styles.emptyText}>暂无待办事项</Text>
            ) : (
              workItems.map((item, index) => (
                <View key={item.id || index} style={styles.taskItem}>
                  <View style={styles.taskCheckbox}>
                    <Ionicons name="time-outline" size={14} color={colors.warning} />
                  </View>
                  <View style={styles.taskContent}>
                    <Text style={styles.taskTitle} numberOfLines={1}>{item.title || item.description}</Text>
                    <Text style={styles.taskTime}>{item.created_at || ''}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.gray3} />
                </View>
              ))
            )}
          </View>
        </Card>

        {/* Recent Alerts */}
        <Card title="最近告警" style={styles.section}>
          <View style={styles.alertList}>
            {(summary as any)?.recent_alerts?.length > 0 ? (
              (summary as any).recent_alerts.slice(0, 3).map((alert: any, index: number) => (
                <View key={index} style={styles.alertItem}>
                  <Ionicons
                    name={alert.severity === 'high' ? 'alert-circle' : alert.severity === 'medium' ? 'warning' : 'information-circle'}
                    size={20}
                    color={alert.severity === 'high' ? colors.error : alert.severity === 'medium' ? colors.warning : colors.info}
                  />
                  <View style={styles.alertContent}>
                    <Text style={styles.alertTitle} numberOfLines={1}>{alert.message || alert.title}</Text>
                    <Text style={styles.alertTime}>{alert.created_at || ''}</Text>
                  </View>
                </View>
              ))
            ) : (
              <Text style={styles.emptyText}>暂无告警</Text>
            )}
          </View>
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xl,
  },
  greeting: {
    ...typography.subhead,
    color: colors.textTertiary,
  },
  title: {
    ...typography.largeTitle,
    color: colors.text,
  },
  notificationButton: {
    width: 44,
    height: 44,
    borderRadius: borderRadius.full,
    backgroundColor: colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    ...shadows.sm,
  },
  notificationBadge: {
    position: 'absolute',
    top: 10,
    right: 10,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.error,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -spacing.xs,
    marginBottom: spacing.lg,
  },
  statCard: {
    width: isTablet ? '25%' : '50%',
    padding: spacing.xs,
  },
  statIconContainer: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  statValue: {
    ...typography.title2,
    color: colors.text,
  },
  statLabel: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  section: {
    marginBottom: spacing.base,
  },
  quickActions: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: spacing.md,
  },
  quickActionItem: {
    alignItems: 'center',
    gap: spacing.sm,
  },
  quickActionIcon: {
    width: 48,
    height: 48,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  quickActionLabel: {
    ...typography.caption1,
    color: colors.text,
    fontWeight: '500',
  },
  taskList: {
    marginTop: spacing.sm,
  },
  taskItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  taskCheckbox: {
    width: 22,
    height: 22,
    borderRadius: borderRadius.sm,
    borderWidth: 2,
    borderColor: colors.warning,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  taskContent: {
    flex: 1,
  },
  taskTitle: {
    ...typography.body,
    color: colors.text,
  },
  taskTime: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  alertList: {
    marginTop: spacing.sm,
  },
  alertItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  alertContent: {
    flex: 1,
    marginLeft: spacing.md,
  },
  alertTitle: {
    ...typography.body,
    color: colors.text,
  },
  alertTime: {
    ...typography.caption2,
    color: colors.textTertiary,
    marginTop: 2,
  },
  emptyText: {
    ...typography.body,
    color: colors.textTertiary,
    textAlign: 'center',
    paddingVertical: spacing.lg,
  },
});

export default WorkbenchScreen;
