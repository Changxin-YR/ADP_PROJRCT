import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Card } from '../../components';
import { Badge } from '../../components/common/Badge';
import { productionApi } from '../../api/production';
import { Batch } from '../../types';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

const BATCH_STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: '#8E8E93' },
  active: { label: '养殖中', color: '#34C759' },
  completed: { label: '已结束', color: '#007AFF' },
  cancelled: { label: '已取消', color: '#FF3B30' },
};

const BatchesScreen: React.FC<any> = ({ navigation }) => {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchBatches = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await productionApi.listBatches(pageNum, 20);
      if (refresh || pageNum === 1) {
        setBatches(data.items);
      } else {
        setBatches((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load batches', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchBatches(1);
  }, [fetchBatches]);

  const loadMore = () => {
    if (hasMore && !loading) fetchBatches(page + 1);
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>养殖批次</Text>
        <TouchableOpacity
          style={styles.addBtn}
          onPress={() => navigation.navigate('BatchCreate')}
        >
          <Ionicons name="add" size={24} color={colors.textInverse} />
        </TouchableOpacity>
      </View>

      {loading && batches.length === 0 ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={batches}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchBatches(1, true)} tintColor={colors.primary} />
          }
          renderItem={({ item }) => {
            const status = BATCH_STATUS_MAP[item.status] || { label: item.status, color: '#8E8E93' };
            return (
              <Card style={styles.batchCard}>
                <View style={styles.batchHeader}>
                  <View style={styles.batchIcon}>
                    <Ionicons name="fish" size={20} color={colors.success} />
                  </View>
                  <Badge label={status.label} color={status.color} />
                </View>
                <Text style={styles.batchPond}>{item.pond_name || `塘口 #${item.pond_id}`}</Text>
                <Text style={styles.batchSpecies}>{item.species || '未设置品种'}</Text>
                <View style={styles.batchMeta}>
                  <View style={styles.batchStat}>
                    <Text style={styles.batchStatValue}>
                      {item.initial_quantity ? `${(item.initial_quantity / 1000).toFixed(1)}K` : '--'}
                    </Text>
                    <Text style={styles.batchStatLabel}>投苗量</Text>
                  </View>
                  <View style={styles.batchStat}>
                    <Text style={styles.batchStatValue}>{item.start_date || '--'}</Text>
                    <Text style={styles.batchStatLabel}>开始日期</Text>
                  </View>
                  <View style={styles.batchStat}>
                    <Text style={styles.batchStatValue}>{item.days_elapsed || 0}</Text>
                    <Text style={styles.batchStatLabel}>养殖天数</Text>
                  </View>
                </View>
              </Card>
            );
          }}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="fish-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无养殖批次</Text>
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
    justifyContent: 'space-between',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: spacing.base,
  },
  addBtn: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    ...shadows.sm,
  },
  title: {
    ...typography.largeTitle,
    color: colors.text,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    padding: layout.screenPadding,
    paddingTop: 0,
  },
  batchCard: {
    marginBottom: spacing.md,
  },
  batchHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  batchIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    backgroundColor: colors.success + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  batchPond: {
    ...typography.headline,
    color: colors.text,
  },
  batchSpecies: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginTop: 2,
  },
  batchMeta: {
    flexDirection: 'row',
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separatorLight,
  },
  batchStat: {
    flex: 1,
    alignItems: 'center',
  },
  batchStatValue: {
    ...typography.headline,
    color: colors.text,
  },
  batchStatLabel: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 1,
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

export default BatchesScreen;
