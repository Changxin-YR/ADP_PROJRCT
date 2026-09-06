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
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

interface Sampling {
  id: number;
  batch_id: number;
  pond_id: number;
  pond_name?: string;
  species?: string;
  sample_count: number;
  avg_weight?: number;
  avg_length?: number;
  estimated_stock?: number;
  sampling_date: string;
  method?: string;
  notes?: string;
  operator_name?: string;
  status: string;
}

const SamplingScreen: React.FC = () => {
  const [samplings, setSamplings] = useState<Sampling[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchSamplings = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await productionApi.listSamplings(pageNum, 20);
      if (refresh || pageNum === 1) {
        setSamplings(data.items);
      } else {
        setSamplings((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load samplings', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchSamplings(1);
  }, [fetchSamplings]);

  const loadMore = () => {
    if (hasMore && !loading) fetchSamplings(page + 1);
  };

  const renderItem = ({ item }: { item: Sampling }) => (
    <Card style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={styles.cardIcon}>
          <Ionicons name="analytics" size={20} color="#5AC8FA" />
        </View>
        <Badge
          label={item.status === 'verified' ? '已确认' : item.status === 'draft' ? '草稿' : '待审'}
          color={item.status === 'verified' ? '#34C759' : item.status === 'draft' ? '#8E8E93' : '#FF9500'}
        />
      </View>
      <Text style={styles.pondName}>{item.pond_name || `塘口 #${item.pond_id}`}</Text>
      <Text style={styles.species}>{item.species || '未设置品种'}</Text>
      <View style={styles.statsRow}>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{item.sample_count}</Text>
          <Text style={styles.statLabel}>样本数</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{item.avg_weight ? `${item.avg_weight}g` : '--'}</Text>
          <Text style={styles.statLabel}>均重</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{item.avg_length ? `${item.avg_length}cm` : '--'}</Text>
          <Text style={styles.statLabel}>均长</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{item.estimated_stock ? `${(item.estimated_stock / 1000).toFixed(1)}K` : '--'}</Text>
          <Text style={styles.statLabel}>估存量</Text>
        </View>
      </View>
      <View style={styles.metaRow}>
        <View style={styles.metaItem}>
          <Ionicons name="calendar-outline" size={13} color={colors.textTertiary} />
          <Text style={styles.metaText}>{item.sampling_date}</Text>
        </View>
        {item.operator_name && (
          <View style={styles.metaItem}>
            <Ionicons name="person-outline" size={13} color={colors.textTertiary} />
            <Text style={styles.metaText}>{item.operator_name}</Text>
          </View>
        )}
        {item.method && (
          <View style={styles.metaItem}>
            <Ionicons name="flask-outline" size={13} color={colors.textTertiary} />
            <Text style={styles.metaText}>{item.method}</Text>
          </View>
        )}
      </View>
    </Card>
  );

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>抽样检测</Text>
        <TouchableOpacity style={styles.addButton}>
          <Ionicons name="add" size={24} color={colors.textInverse} />
        </TouchableOpacity>
      </View>

      {loading && samplings.length === 0 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={samplings}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchSamplings(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="analytics-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无抽样记录</Text>
              <Text style={styles.emptySubtext}>对养殖批次进行抽样检测，追踪生长和健康状况</Text>
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
  addButton: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    ...shadows.sm,
  },
  listContent: {
    padding: layout.screenPadding,
    paddingTop: 0,
  },
  card: {
    marginBottom: spacing.md,
    padding: spacing.base,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  cardIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    backgroundColor: '#5AC8FA' + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pondName: {
    ...typography.headline,
    color: colors.text,
  },
  species: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginTop: 2,
    marginBottom: spacing.md,
  },
  statsRow: {
    flexDirection: 'row',
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separatorLight,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statValue: {
    ...typography.headline,
    color: colors.text,
  },
  statLabel: {
    ...typography.caption2,
    color: colors.textTertiary,
    marginTop: 2,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  metaText: {
    ...typography.caption1,
    color: colors.textTertiary,
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
  emptySubtext: {
    ...typography.caption1,
    color: colors.gray3,
    marginTop: spacing.xs,
  },
});

export default SamplingScreen;
