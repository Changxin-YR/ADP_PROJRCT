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
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Badge } from '../../components/common/Badge';
import { SearchBar } from '../../components/common/SearchBar';
import { warehouseApi } from '../../api/warehouse';
import { WarehouseDocument } from '../../types';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

type ReceiptListScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

const statusConfig: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: '#8E8E93' },
  submitted: { label: '已提交', color: '#FF9500' },
  verified: { label: '已核验', color: '#007AFF' },
  confirmed: { label: '已确认', color: '#34C759' },
};

const ReceiptListScreen: React.FC<ReceiptListScreenProps> = ({ navigation }) => {
  const [search, setSearch] = useState('');
  const [receipts, setReceipts] = useState<WarehouseDocument[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchReceipts = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await warehouseApi.listReceipts(pageNum, 20);
      if (refresh || pageNum === 1) {
        setReceipts(data.items);
      } else {
        setReceipts((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load receipts', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchReceipts(1);
  }, [fetchReceipts]);

  const filtered = receipts.filter(
    (r) => (r.code || '').toLowerCase().includes(search.toLowerCase()) ||
           (r.name || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>入库单</Text>
        <TouchableOpacity style={styles.addBtn}>
          <Ionicons name="add" size={24} color={colors.primary} />
        </TouchableOpacity>
      </View>
      <View style={styles.searchContainer}>
        <SearchBar value={search} onChangeText={setSearch} placeholder="搜索入库单..." />
      </View>
      {loading && receipts.length === 0 ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(item) => String(item.id)}
          renderItem={({ item }) => {
            const status = statusConfig[item.status] || statusConfig.draft;
            return (
              <TouchableOpacity style={styles.receiptCard} activeOpacity={0.7}>
                <View style={styles.receiptHeader}>
                  <Text style={styles.receiptCode}>{item.code}</Text>
                  <Badge label={status.label} color={status.color} />
                </View>
                <Text style={styles.supplierName}>{item.name || '-'}</Text>
                <View style={styles.receiptFooter}>
                  <Text style={styles.receiptMeta}>{item.created_at?.split('T')[0]}</Text>
                  <Text style={styles.receiptAmount}>v{item.version}</Text>
                </View>
              </TouchableOpacity>
            );
          }}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={() => {
            if (hasMore && !loading) fetchReceipts(page + 1);
          }}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchReceipts(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="document-text-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无入库单</Text>
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
  },
  backBtn: {
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
    marginLeft: spacing.md,
  },
  addBtn: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchContainer: {
    paddingHorizontal: layout.screenPadding,
    marginBottom: spacing.md,
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
  receiptCard: {
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    marginBottom: spacing.md,
    ...shadows.sm,
  },
  receiptHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  receiptCode: {
    ...typography.headline,
    color: colors.text,
  },
  supplierName: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginBottom: spacing.md,
  },
  receiptFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separatorLight,
  },
  receiptMeta: {
    ...typography.caption1,
    color: colors.textTertiary,
  },
  receiptAmount: {
    ...typography.caption1,
    color: colors.textTertiary,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingTop: 80,
  },
  emptyText: {
    ...typography.body,
    color: colors.textTertiary,
    marginTop: spacing.md,
  },
});

export default ReceiptListScreen;
