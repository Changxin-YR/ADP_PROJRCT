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
import { Card } from '../../components';
import { Badge } from '../../components/common/Badge';
import { warehouseApi } from '../../api/warehouse';
import { WarehouseDocument, DOCUMENT_STATUS_LABELS, DOCUMENT_STATUS_COLORS } from '../../types';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const ScrapsScreen: React.FC<Props> = ({ navigation }) => {
  const [items, setItems] = useState<WarehouseDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchData = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await warehouseApi.listScraps(pageNum, 20);
      if (refresh || pageNum === 1) {
        setItems(data.items);
      } else {
        setItems((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load scraps', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData(1);
  }, [fetchData]);

  const loadMore = () => {
    if (hasMore && !loading) fetchData(page + 1);
  };

  const renderItem = ({ item }: { item: WarehouseDocument }) => (
    <Card style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={styles.iconWrap}>
          <Ionicons name="trash" size={20} color="#FF3B30" />
        </View>
        <View style={styles.cardHeaderText}>
          <Text style={styles.code}>{item.code}</Text>
          <Text style={styles.dateText}>{item.created_at?.split('T')[0]}</Text>
        </View>
        <Badge
          label={DOCUMENT_STATUS_LABELS[item.status] || item.status}
          color={DOCUMENT_STATUS_COLORS[item.status] || '#8E8E93'}
        />
      </View>
      <Text style={styles.nameText}>{item.name || '报损报废'}</Text>
    </Card>
  );

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>报损报废</Text>
        <View style={{ width: 36 }} />
      </View>

      {loading && items.length === 0 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchData(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="trash-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无报损报废记录</Text>
            </View>
          }
        />
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.backgroundSecondary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: layout.screenPadding, paddingVertical: spacing.base },
  backBtn: { width: 36, height: 36, borderRadius: borderRadius.full, justifyContent: 'center', alignItems: 'center' },
  title: { ...typography.headline, color: colors.text, flex: 1, textAlign: 'center' },
  listContent: { padding: layout.screenPadding, paddingTop: 0 },
  card: { marginBottom: spacing.md, padding: spacing.base },
  cardHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.sm },
  iconWrap: { width: 36, height: 36, borderRadius: borderRadius.md, backgroundColor: '#FF3B3015', justifyContent: 'center', alignItems: 'center', marginRight: spacing.md },
  cardHeaderText: { flex: 1 },
  code: { ...typography.headline, color: colors.text },
  dateText: { ...typography.caption1, color: colors.textTertiary, marginTop: 2 },
  nameText: { ...typography.subhead, color: colors.textSecondary },
  emptyContainer: { alignItems: 'center', paddingVertical: spacing.xxl },
  emptyText: { ...typography.body, color: colors.textTertiary, marginTop: spacing.md },
});

export default ScrapsScreen;
