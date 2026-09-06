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

interface TransferRecord {
  id: number;
  batch_id: number;
  source_pond_id: number;
  source_pond_name?: string;
  target_pond_id: number;
  target_pond_name?: string;
  species?: string;
  quantity?: number;
  weight?: number;
  transfer_date: string;
  reason?: string;
  operator_name?: string;
  status: string;
}

const TransfersScreen: React.FC<any> = ({ navigation }) => {
  const [transfers, setTransfers] = useState<TransferRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchTransfers = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await productionApi.listTransfers(pageNum, 20);
      if (refresh || pageNum === 1) {
        setTransfers(data.items);
      } else {
        setTransfers((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load transfers', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchTransfers(1);
  }, [fetchTransfers]);

  const loadMore = () => {
    if (hasMore && !loading) fetchTransfers(page + 1);
  };

  const renderItem = ({ item }: { item: TransferRecord }) => (
    <Card style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={styles.typeIcon}>
          <Ionicons name="swap-horizontal" size={20} color="#AF52DE" />
        </View>
        <View style={styles.cardHeaderText}>
          <Text style={styles.dateText}>{item.transfer_date}</Text>
        </View>
        <Badge
          label={item.status === 'confirmed' ? '已确认' : item.status === 'completed' ? '已完成' : '待确认'}
          color={item.status === 'confirmed' || item.status === 'completed' ? '#34C759' : '#FF9500'}
        />
      </View>
      <View style={styles.transferFlow}>
        <View style={styles.pondBox}>
          <Ionicons name="water-outline" size={16} color={colors.error} />
          <Text style={styles.pondLabel}>{item.source_pond_name || `塘口 #${item.source_pond_id}`}</Text>
        </View>
        <Ionicons name="arrow-forward" size={18} color={colors.textTertiary} />
        <View style={styles.pondBox}>
          <Ionicons name="water-outline" size={16} color={colors.success} />
          <Text style={styles.pondLabel}>{item.target_pond_name || `塘口 #${item.target_pond_id}`}</Text>
        </View>
      </View>
      <View style={styles.metaRow}>
        {item.quantity != null && <Text style={styles.metaText}>数量: {item.quantity} 尾</Text>}
        {item.weight != null && <Text style={styles.metaText}>重量: {item.weight} kg</Text>}
        {item.operator_name && <Text style={styles.metaText}>经办: {item.operator_name}</Text>}
      </View>
      {item.reason && <Text style={styles.reasonText}>原因: {item.reason}</Text>}
    </Card>
  );

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>转塘记录</Text>
        <TouchableOpacity style={styles.addBtn}>
          <Ionicons name="add" size={24} color={colors.textInverse} />
        </TouchableOpacity>
      </View>

      {loading && transfers.length === 0 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={transfers}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchTransfers(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="swap-horizontal-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无转塘记录</Text>
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
    backgroundColor: '#AF52DE' + '15',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  cardHeaderText: {
    flex: 1,
  },
  dateText: {
    ...typography.subhead,
    color: colors.textTertiary,
  },
  transferFlow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    backgroundColor: colors.backgroundSecondary,
    borderRadius: borderRadius.md,
    marginBottom: spacing.sm,
  },
  pondBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  pondLabel: {
    ...typography.body,
    color: colors.text,
    fontWeight: '500',
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  metaText: {
    ...typography.caption1,
    color: colors.textTertiary,
  },
  reasonText: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: spacing.xs,
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

export default TransfersScreen;
