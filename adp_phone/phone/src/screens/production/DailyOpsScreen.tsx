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
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Card } from '../../components';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';
import { FeedingStackParamList } from '../../navigation/FeedingStack';
import { productionApi } from '../../api/production';
import { DailyOperation } from '../../types';

type DailyOpsScreenProps = {
  navigation: NativeStackNavigationProp<FeedingStackParamList, 'DailyOps'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const OP_TYPE_MAP: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string; label: string }> = {
  patrol: { icon: 'eye-outline', color: '#007AFF', label: '巡塘' },
  water_quality: { icon: 'water-outline', color: '#5AC8FA', label: '水质检测' },
  medication: { icon: 'medical-outline', color: '#FF2D55', label: '用药' },
  aeration: { icon: 'cloudy-outline', color: '#34C759', label: '增氧' },
  transfer: { icon: 'swap-horizontal-outline', color: '#AF52DE', label: '转塘' },
  harvest: { icon: 'fish-outline', color: '#FF9500', label: '捕捞' },
  other: { icon: 'ellipsis-horizontal-outline', color: '#8E8E93', label: '其他' },
};

const DailyOpsScreen: React.FC<DailyOpsScreenProps> = ({ navigation }) => {
  const [operations, setOperations] = useState<DailyOperation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);

  const fetchOps = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await productionApi.listDailyOps(pageNum, 20);
      if (refresh || pageNum === 1) {
        setOperations(data.items);
      } else {
        setOperations((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load daily operations', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchOps(1);
  }, [fetchOps]);

  const loadMore = () => {
    if (hasMore && !loading) {
      fetchOps(page + 1);
    }
  };

  const typeFilters = [
    { key: undefined, label: '全部' },
    { key: 'patrol', label: '巡塘' },
    { key: 'medication', label: '用药' },
    { key: 'aeration', label: '增氧' },
    { key: 'water_quality', label: '水质' },
  ];

  const filteredOps = typeFilter
    ? operations.filter(op => op.operation_type === typeFilter)
    : operations;

  const renderOpCard = ({ item, index }: { item: DailyOperation; index: number }) => {
    const opType = OP_TYPE_MAP[item.operation_type || 'other'] || OP_TYPE_MAP.other;
    return (
      <Animated.View entering={FadeInDown.delay(index * 50).duration(300)}>
        <Card style={styles.opCard}>
          <View style={styles.opHeader}>
            <View style={[styles.opIcon, { backgroundColor: opType.color + '15' }]}>
              <Ionicons name={opType.icon} size={20} color={opType.color} />
            </View>
            <View style={styles.opHeaderText}>
              <Text style={styles.opType}>{opType.label}</Text>
              <Text style={styles.opTime}>{item.operation_date || item.created_at || ''}</Text>
            </View>
          </View>
          {item.pond_name && (
            <View style={styles.opMeta}>
              <Ionicons name="location-outline" size={14} color={colors.textTertiary} />
              <Text style={styles.opMetaText}>{item.pond_name}</Text>
            </View>
          )}
          {item.description && (
            <Text style={styles.opDesc} numberOfLines={2}>{item.description}</Text>
          )}
          {item.observations && (
            <Text style={styles.opDesc} numberOfLines={2}>{item.observations}</Text>
          )}
        </Card>
      </Animated.View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>日常操作</Text>
        <TouchableOpacity style={styles.addButton} onPress={() => navigation.navigate('DailyOpsCreate')}>
          <Ionicons name="add" size={24} color={colors.textInverse} />
        </TouchableOpacity>
      </View>

      {/* Type Filter */}
      <View style={styles.filterRow}>
        {typeFilters.map((f) => (
          <TouchableOpacity
            key={f.key || 'all'}
            style={[styles.filterChip, typeFilter === f.key && styles.filterChipActive]}
            onPress={() => setTypeFilter(f.key)}
          >
            <Text style={[styles.filterText, typeFilter === f.key && styles.filterTextActive]}>
              {f.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Operations List */}
      {loading && page === 1 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={filteredOps}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          renderItem={renderOpCard}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchOps(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="clipboard-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无操作记录</Text>
              <Text style={styles.emptySubtext}>点击右上角 + 新增日常操作记录</Text>
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
  opCard: {
    marginBottom: spacing.md,
    padding: spacing.base,
  },
  opHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  opIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  opHeaderText: {
    flex: 1,
  },
  opType: {
    ...typography.headline,
    color: colors.text,
  },
  opTime: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  opMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginBottom: spacing.sm,
  },
  opMetaText: {
    ...typography.caption1,
    color: colors.textTertiary,
  },
  opDesc: {
    ...typography.body,
    color: colors.textSecondary,
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

export default DailyOpsScreen;
