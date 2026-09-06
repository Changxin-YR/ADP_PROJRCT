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

interface LossRecord {
  id: number;
  batch_id: number;
  pond_id: number;
  pond_name?: string;
  species?: string;
  loss_type: string;
  quantity?: number;
  weight?: number;
  loss_date: string;
  reason?: string;
  discoverer?: string;
  status: string;
}

const LOSS_TYPE_MAP: Record<string, { label: string; icon: string; color: string }> = {
  death: { label: '死亡', icon: 'skull-outline', color: '#FF3B30' },
  escape: { label: '逃逸', icon: 'exit-outline', color: '#FF9500' },
  disease: { label: '疾病', icon: 'medical-outline', color: '#AF52DE' },
  sampling: { label: '抽样损耗', icon: 'flask-outline', color: '#5AC8FA' },
  damage: { label: '报损', icon: 'alert-circle-outline', color: '#8E8E93' },
  other: { label: '其他', icon: 'ellipsis-horizontal-outline', color: '#8E8E93' },
};

const LossesScreen: React.FC<any> = ({ navigation }) => {
  const [losses, setLosses] = useState<LossRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchLosses = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await productionApi.listLosses(pageNum, 20);
      if (refresh || pageNum === 1) {
        setLosses(data.items);
      } else {
        setLosses((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load losses', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchLosses(1);
  }, [fetchLosses]);

  const loadMore = () => {
    if (hasMore && !loading) fetchLosses(page + 1);
  };

  const renderItem = ({ item }: { item: LossRecord }) => {
    const typeInfo = LOSS_TYPE_MAP[item.loss_type] || LOSS_TYPE_MAP.other;
    return (
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={[styles.typeIcon, { backgroundColor: typeInfo.color + '15' }]}>
            <Ionicons name={typeInfo.icon as any} size={20} color={typeInfo.color} />
          </View>
          <View style={styles.cardHeaderText}>
            <Text style={styles.typeLabel}>{typeInfo.label}</Text>
            <Text style={styles.dateText}>{item.loss_date}</Text>
          </View>
          <Badge
            label={item.status === 'confirmed' ? '已确认' : '待确认'}
            color={item.status === 'confirmed' ? '#34C759' : '#FF9500'}
          />
        </View>
        <View style={styles.cardBody}>
          <Text style={styles.pondName}>{item.pond_name || `塘口 #${item.pond_id}`}</Text>
          {item.quantity && <Text style={styles.quantityText}>数量: {item.quantity} 尾</Text>}
          {item.weight && <Text style={styles.quantityText}>重量: {item.weight} kg</Text>}
          {item.reason && <Text style={styles.reasonText} numberOfLines={2}>原因: {item.reason}</Text>}
        </View>
      </Card>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>损耗记录</Text>
        <TouchableOpacity style={styles.addBtn}>
          <Ionicons name="add" size={24} color={colors.textInverse} />
        </TouchableOpacity>
      </View>

      {loading && losses.length === 0 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={losses}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchLosses(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="trending-down-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无损耗记录</Text>
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
    marginBottom: spacing.sm,
  },
  typeIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  cardHeaderText: {
    flex: 1,
  },
  typeLabel: {
    ...typography.headline,
    color: colors.text,
  },
  dateText: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  cardBody: {
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separatorLight,
  },
  pondName: {
    ...typography.body,
    color: colors.text,
    fontWeight: '500',
  },
  quantityText: {
    ...typography.subhead,
    color: colors.textSecondary,
    marginTop: 4,
  },
  reasonText: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 4,
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

export default LossesScreen;
