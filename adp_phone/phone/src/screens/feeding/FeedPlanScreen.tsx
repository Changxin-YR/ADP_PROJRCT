import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Dimensions,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Card } from '../../components';
import { Badge } from '../../components/common/Badge';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';
import { FeedingStackParamList } from '../../navigation/FeedingStack';
import { feedingApi } from '../../api/feeding';
import { FeedPlan } from '../../types';

type FeedPlanScreenProps = {
  navigation: NativeStackNavigationProp<FeedingStackParamList, 'FeedPlanList'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: '#8E8E93' },
  submitted: { label: '已提交', color: '#007AFF' },
  approved: { label: '已审批', color: '#34C759' },
  active: { label: '执行中', color: '#FF9500' },
  completed: { label: '已完成', color: '#34C759' },
  cancelled: { label: '已取消', color: '#FF3B30' },
};

const FeedPlanScreen: React.FC<FeedPlanScreenProps> = ({ navigation }) => {
  const [plans, setPlans] = useState<FeedPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  const fetchPlans = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await feedingApi.listPlans(pageNum, 20, statusFilter);
      if (refresh || pageNum === 1) {
        setPlans(data.items);
      } else {
        setPlans((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load feed plans', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchPlans(1);
  }, [fetchPlans]);

  const loadMore = () => {
    if (hasMore && !loading) {
      fetchPlans(page + 1);
    }
  };

  const statusFilters = [
    { key: undefined, label: '全部' },
    { key: 'active', label: '执行中' },
    { key: 'draft', label: '草稿' },
    { key: 'completed', label: '已完成' },
  ];

  const renderPlanCard = ({ item }: { item: FeedPlan }) => {
    const status = STATUS_MAP[item.status] || { label: item.status, color: '#8E8E93' };
    return (
      <Card style={styles.planCard}>
        <View style={styles.planHeader}>
          <View style={styles.planIcon}>
            <Ionicons name="nutrition" size={20} color={colors.warning} />
          </View>
          <Badge label={status.label} color={status.color} />
        </View>
        <Text style={styles.planName} numberOfLines={1}>{item.name || `投喂计划 #${item.id}`}</Text>
        <View style={styles.planMeta}>
          <View style={styles.metaItem}>
            <Ionicons name="water-outline" size={14} color={colors.textTertiary} />
            <Text style={styles.metaText}>{item.pond_name || `塘口${item.pond_id}`}</Text>
          </View>
          <View style={styles.metaItem}>
            <Ionicons name="calendar-outline" size={14} color={colors.textTertiary} />
            <Text style={styles.metaText}>{item.start_date || '--'}</Text>
          </View>
        </View>
        <View style={styles.planStats}>
          <View style={styles.planStatItem}>
            <Text style={styles.planStatValue}>{item.daily_amount || 0}</Text>
            <Text style={styles.planStatLabel}>日投喂量(kg)</Text>
          </View>
          <View style={styles.planStatItem}>
            <Text style={styles.planStatValue}>{item.frequency || 0}</Text>
            <Text style={styles.planStatLabel}>日投喂次数</Text>
          </View>
          <View style={styles.planStatItem}>
            <Text style={styles.planStatValue}>{item.feed_type || '--'}</Text>
            <Text style={styles.planStatLabel}>饲料类型</Text>
          </View>
        </View>
      </Card>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>投喂计划</Text>
        <View style={styles.headerActions}>
          <TouchableOpacity
            style={styles.headerButton}
            onPress={() => navigation.navigate('FeedPlanCreate')}
          >
            <Ionicons name="add-circle-outline" size={22} color={colors.primary} />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.headerButton}
            onPress={() => navigation.navigate('DailyOps')}
          >
            <Ionicons name="clipboard-outline" size={22} color={colors.primary} />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.headerButton}
            onPress={() => navigation.navigate('FeedLog')}
          >
            <Ionicons name="list-outline" size={22} color={colors.primary} />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.headerButton}
            onPress={() => navigation.navigate('FeedTasks')}
          >
            <Ionicons name="checkbox-outline" size={22} color={colors.primary} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Status Filter */}
      <View style={styles.filterRow}>
        {statusFilters.map((f) => (
          <TouchableOpacity
            key={f.key || 'all'}
            style={[styles.filterChip, statusFilter === f.key && styles.filterChipActive]}
            onPress={() => setStatusFilter(f.key)}
          >
            <Text style={[styles.filterText, statusFilter === f.key && styles.filterTextActive]}>
              {f.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Plan List */}
      {loading && page === 1 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={plans}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          numColumns={isTablet ? 2 : 1}
          renderItem={renderPlanCard}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchPlans(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="nutrition-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无投喂计划</Text>
            </View>
          }
        />
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundSecondary,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: spacing.base,
  },
  title: {
    ...typography.largeTitle,
    color: colors.text,
  },
  headerActions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  headerButton: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    backgroundColor: colors.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: layout.screenPadding,
    marginBottom: spacing.md,
    gap: spacing.sm,
  },
  filterChip: {
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    backgroundColor: colors.background,
  },
  filterChipActive: {
    backgroundColor: colors.primary,
  },
  filterText: {
    ...typography.subhead,
    color: colors.textSecondary,
  },
  filterTextActive: {
    color: colors.textInverse,
    fontWeight: '600',
  },
  listContent: {
    padding: layout.screenPadding,
    paddingTop: 0,
  },
  planCard: {
    flex: 1,
    margin: spacing.xs,
    padding: spacing.base,
  },
  planHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  planIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    backgroundColor: colors.warning + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  planName: {
    ...typography.headline,
    color: colors.text,
    marginBottom: spacing.sm,
  },
  planMeta: {
    flexDirection: 'row',
    gap: spacing.base,
    marginBottom: spacing.md,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metaText: {
    ...typography.caption1,
    color: colors.textTertiary,
  },
  planStats: {
    flexDirection: 'row',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separatorLight,
    paddingTop: spacing.md,
  },
  planStatItem: {
    flex: 1,
    alignItems: 'center',
  },
  planStatValue: {
    ...typography.headline,
    color: colors.text,
  },
  planStatLabel: {
    ...typography.caption2,
    color: colors.textTertiary,
    marginTop: 2,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: spacing.xxl,
  },
  emptyText: {
    ...typography.body,
    color: colors.textTertiary,
    marginTop: spacing.md,
  },
});

export default FeedPlanScreen;
