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

interface HarvestRecord {
  id: number;
  batch_id: number;
  pond_id: number;
  pond_name?: string;
  species?: string;
  quantity?: number;
  weight?: number;
  harvest_date: string;
  destination?: string;
  unit_price?: number;
  total_amount?: number;
  operator_name?: string;
  status: string;
}

const HarvestsScreen: React.FC<any> = ({ navigation }) => {
  const [harvests, setHarvests] = useState<HarvestRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchHarvests = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await productionApi.listHarvests(pageNum, 20);
      if (refresh || pageNum === 1) {
        setHarvests(data.items);
      } else {
        setHarvests((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load harvests', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchHarvests(1);
  }, [fetchHarvests]);

  const loadMore = () => {
    if (hasMore && !loading) fetchHarvests(page + 1);
  };

  const renderItem = ({ item }: { item: HarvestRecord }) => (
    <Card style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={styles.typeIcon}>
          <Ionicons name="fish" size={20} color="#FF9500" />
        </View>
        <View style={styles.cardHeaderText}>
          <Text style={styles.pondName}>{item.pond_name || `塘口 #${item.pond_id}`}</Text>
          <Text style={styles.dateText}>{item.harvest_date}</Text>
        </View>
        <Badge
          label={item.status === 'confirmed' ? '已确认' : item.status === 'sold' ? '已销售' : '待确认'}
          color={item.status === 'confirmed' ? '#34C759' : item.status === 'sold' ? '#007AFF' : '#FF9500'}
        />
      </View>
      <View style={styles.statsRow}>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{item.quantity || '--'}</Text>
          <Text style={styles.statLabel}>数量(尾)</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{item.weight || '--'}</Text>
          <Text style={styles.statLabel}>重量(kg)</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{item.unit_price ? `¥${item.unit_price}` : '--'}</Text>
          <Text style={styles.statLabel}>单价</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={[styles.statValue, { color: colors.success }]}>
            {item.total_amount ? `¥${item.total_amount.toFixed(0)}` : '--'}
          </Text>
          <Text style={styles.statLabel}>金额</Text>
        </View>
      </View>
      {(item.destination || item.operator_name) && (
        <View style={styles.metaRow}>
          {item.destination && <Text style={styles.metaText}>去向: {item.destination}</Text>}
          {item.operator_name && <Text style={styles.metaText}>经办: {item.operator_name}</Text>}
        </View>
      )}
    </Card>
  );

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>出塘记录</Text>
        <TouchableOpacity style={styles.addBtn}>
          <Ionicons name="add" size={24} color={colors.textInverse} />
        </TouchableOpacity>
      </View>

      {loading && harvests.length === 0 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={harvests}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchHarvests(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="fish-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无出塘记录</Text>
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
    paddingVertical: spacing.base,
  },
  backBtn: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    ...typography.headline,
    color: colors.text,
    flex: 1,
    textAlign: 'center',
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
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  typeIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    backgroundColor: '#FF9500' + '15',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  cardHeaderText: {
    flex: 1,
  },
  pondName: {
    ...typography.headline,
    color: colors.text,
  },
  dateText: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  statsRow: {
    flexDirection: 'row',
    paddingVertical: spacing.md,
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
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separatorLight,
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
});

export default HarvestsScreen;
