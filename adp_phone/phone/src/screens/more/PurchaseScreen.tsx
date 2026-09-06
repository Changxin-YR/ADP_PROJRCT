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
import { purchaseApi } from '../../api/purchase';
import { PurchaseOrder, DOCUMENT_STATUS_LABELS, DOCUMENT_STATUS_COLORS } from '../../types';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

type PurchaseScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

const PurchaseScreen: React.FC<PurchaseScreenProps> = ({ navigation }) => {
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchOrders = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      const data = await purchaseApi.listOrders(pageNum, 20);
      if (refresh || pageNum === 1) {
        setOrders(data.items);
      } else {
        setOrders((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load purchase orders', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders(1);
  }, [fetchOrders]);

  const onRefresh = useCallback(() => {
    fetchOrders(1, true);
  }, [fetchOrders]);

  const onEndReached = useCallback(() => {
    if (hasMore && !loading) {
      fetchOrders(page + 1);
    }
  }, [hasMore, loading, page, fetchOrders]);

  const renderItem = ({ item }: { item: PurchaseOrder }) => (
    <TouchableOpacity style={styles.orderCard} activeOpacity={0.7}>
      <View style={styles.orderHeader}>
        <Text style={styles.orderCode}>{item.code}</Text>
        <Badge
          label={DOCUMENT_STATUS_LABELS[item.status] || item.status}
          color={DOCUMENT_STATUS_COLORS[item.status] || '#8E8E93'}
        />
      </View>
      <Text style={styles.supplierName}>{item.name}</Text>
      <View style={styles.orderFooter}>
        <Text style={styles.orderDate}>{item.created_at?.split('T')[0]}</Text>
        <Text style={styles.orderVersion}>v{item.version}</Text>
      </View>
    </TouchableOpacity>
  );

  if (loading && orders.length === 0) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.title}>采购管理</Text>
          <View style={{ width: 36 }} />
        </View>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>采购管理</Text>
        <View style={{ width: 36 }} />
      </View>
      <FlatList
        data={orders}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderItem}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        onEndReached={onEndReached}
        onEndReachedThreshold={0.3}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="cart-outline" size={48} color={colors.gray3} />
            <Text style={styles.emptyText}>暂无采购订单</Text>
          </View>
        }
      />
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
  title: {
    ...typography.headline,
    color: colors.text,
    flex: 1,
    textAlign: 'center',
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
  orderCard: {
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    marginBottom: spacing.md,
    ...shadows.sm,
  },
  orderHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  orderCode: {
    ...typography.headline,
    color: colors.text,
  },
  supplierName: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginBottom: spacing.md,
  },
  orderFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separatorLight,
  },
  orderDate: {
    ...typography.caption1,
    color: colors.textTertiary,
  },
  orderVersion: {
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

export default PurchaseScreen;
