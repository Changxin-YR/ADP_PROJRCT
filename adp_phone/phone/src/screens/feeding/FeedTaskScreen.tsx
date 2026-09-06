import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';
import { FeedingStackParamList } from '../../navigation/FeedingStack';
import { feedingApi } from '../../api/feeding';
import { FeedTask } from '../../types';

type FeedTaskScreenProps = {
  navigation: NativeStackNavigationProp<FeedingStackParamList, 'FeedTasks'>;
};

const TASK_STATUS_MAP: Record<string, { label: string; icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  pending: { label: '待执行', icon: 'ellipse-outline', color: '#8E8E93' },
  in_progress: { label: '执行中', icon: 'time-outline', color: '#FF9500' },
  awaiting_review: { label: '待核验', icon: 'hourglass-outline', color: '#5AC8FA' },
  verified: { label: '已核验', icon: 'checkmark-circle', color: '#34C759' },
  reviewed: { label: '已复盘', icon: 'checkmark-done-circle', color: '#007AFF' },
  cancelled: { label: '已取消', icon: 'close-circle', color: '#FF3B30' },
  completed: { label: '已完成', icon: 'checkmark-circle', color: '#34C759' },
};

const FeedTaskScreen: React.FC<FeedTaskScreenProps> = ({ navigation }) => {
  const [tasks, setTasks] = useState<FeedTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  const fetchTasks = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await feedingApi.listTasks(pageNum, 20, statusFilter);
      if (refresh || pageNum === 1) {
        setTasks(data.items);
      } else {
        setTasks((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load feed tasks', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchTasks(1);
  }, [fetchTasks]);

  const loadMore = () => {
    if (hasMore && !loading) {
      fetchTasks(page + 1);
    }
  };

  const handleSubmitTask = async (task: FeedTask) => {
    Alert.alert('确认提交', `确认完成「${task.pond_name || ''}」的投喂任务？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '确认',
        onPress: async () => {
          try {
            await feedingApi.submitTask(task.id, task.version || 1);
            fetchTasks(1, true);
          } catch (err) {
            Alert.alert('提交失败', '请稍后重试');
          }
        },
      },
    ]);
  };

  const statusFilters = [
    { key: undefined, label: '全部' },
    { key: 'pending', label: '待执行' },
    { key: 'in_progress', label: '执行中' },
    { key: 'awaiting_review', label: '待核验' },
    { key: 'verified', label: '已核验' },
  ];

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>投喂任务</Text>
        <View style={{ width: 36 }} />
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

      {loading && page === 1 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={tasks}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchTasks(1, true)} tintColor={colors.primary} />
          }
          renderItem={({ item }) => {
            const status = TASK_STATUS_MAP[item.status] || TASK_STATUS_MAP.pending;
            return (
              <TouchableOpacity style={styles.taskItem} activeOpacity={0.7}>
                <Ionicons name={status.icon} size={24} color={status.color} />
                <View style={styles.taskContent}>
                  <Text style={styles.taskPond}>{item.pond_name || `塘口 #${item.pond_id}`}</Text>
                  <Text style={styles.taskDetail}>
                    {item.feed_amount || 0}kg · {item.scheduled_time || ''}
                  </Text>
                  <Text style={styles.taskStatus}>{status.label}</Text>
                </View>
                {(item.status as string) === 'pending' && (
                  <TouchableOpacity
                    style={styles.completeButton}
                    onPress={() => handleSubmitTask(item)}
                  >
                    <Text style={styles.completeText}>执行</Text>
                  </TouchableOpacity>
                )}
              </TouchableOpacity>
            );
          }}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="checkbox-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无投喂任务</Text>
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
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  backButton: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    ...typography.headline,
    color: colors.text,
    flex: 1,
    textAlign: 'center',
  },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: spacing.md,
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
    ...typography.caption1,
    color: colors.textSecondary,
  },
  filterTextActive: {
    color: colors.textInverse,
    fontWeight: '600',
  },
  listContent: {
    padding: layout.screenPadding,
  },
  taskItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.base,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  taskContent: {
    flex: 1,
    marginLeft: spacing.md,
  },
  taskPond: {
    ...typography.body,
    color: colors.text,
    fontWeight: '500',
  },
  taskDetail: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginTop: 2,
  },
  taskStatus: {
    ...typography.caption2,
    color: colors.textSecondary,
    marginTop: 2,
  },
  completeButton: {
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    backgroundColor: colors.primary + '15',
    borderRadius: borderRadius.full,
  },
  completeText: {
    ...typography.subhead,
    color: colors.primary,
    fontWeight: '600',
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

export default FeedTaskScreen;
