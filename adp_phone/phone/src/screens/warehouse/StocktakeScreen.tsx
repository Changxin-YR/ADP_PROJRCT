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
import { SearchBar } from '../../components/common/SearchBar';
import { warehouseApi } from '../../api/warehouse';
import { masterDataApi } from '../../api/masterData';
import { Material } from '../../types';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

type StocktakeScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

interface StockItem extends Material {
  actualQty?: number;
  checked: boolean;
}

const StocktakeScreen: React.FC<StocktakeScreenProps> = ({ navigation }) => {
  const [search, setSearch] = useState('');
  const [items, setItems] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchMaterials = useCallback(async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      const data = await masterDataApi.listMaterials(1, 100);
      const stockItems: StockItem[] = data.items.map((m) => ({
        ...m,
        checked: false,
        actualQty: undefined,
      }));
      setItems(stockItems);
    } catch (err) {
      console.warn('Failed to load materials for stocktake', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchMaterials();
  }, [fetchMaterials]);

  const toggleCheck = (id: number) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, checked: !item.checked, actualQty: item.checked ? undefined : 0 } : item
      )
    );
  };

  const checkedCount = items.filter((i) => i.checked).length;
  const filtered = items.filter((i) =>
    i.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>盘点</Text>
        <TouchableOpacity style={styles.saveBtn}>
          <Text style={styles.saveBtnText}>保存</Text>
        </TouchableOpacity>
      </View>

      {/* Progress */}
      <View style={styles.progressContainer}>
        <Text style={styles.progressText}>{checkedCount}/{items.length} 项已盘点</Text>
        <View style={styles.progressBar}>
          <View style={[styles.progressFill, { width: items.length > 0 ? `${(checkedCount / items.length) * 100}%` : '0%' }]} />
        </View>
      </View>

      <View style={styles.searchContainer}>
        <SearchBar value={search} onChangeText={setSearch} placeholder="搜索物料..." />
      </View>

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(item) => String(item.id)}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchMaterials(true)} tintColor={colors.primary} />
          }
          renderItem={({ item }) => (
            <TouchableOpacity style={styles.stockItem} onPress={() => toggleCheck(item.id)} activeOpacity={0.7}>
              <View style={styles.itemLeft}>
                <View style={[styles.checkCircle, item.checked && styles.checkCircleActive]}>
                  {item.checked && <Ionicons name="checkmark" size={14} color={colors.textInverse} />}
                </View>
                <View>
                  <Text style={styles.itemName}>{item.name}</Text>
                  <Text style={styles.itemCategory}>{item.category} | {item.unit}</Text>
                </View>
              </View>
              <View style={styles.itemRight}>
                <Text style={styles.systemQty}>安全库存: {item.safety_stock}</Text>
                {item.actualQty !== undefined && (
                  <Text style={[
                    styles.actualQty,
                    item.actualQty !== item.safety_stock && styles.qtyDiff,
                  ]}>
                    实际: {item.actualQty}
                  </Text>
                )}
              </View>
            </TouchableOpacity>
          )}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="clipboard-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无物料可盘点</Text>
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
  saveBtn: {
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    backgroundColor: colors.primary,
    borderRadius: borderRadius.md,
  },
  saveBtnText: {
    ...typography.subhead,
    color: colors.textInverse,
    fontWeight: '600',
  },
  progressContainer: {
    paddingHorizontal: layout.screenPadding,
    marginBottom: spacing.md,
  },
  progressText: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginBottom: spacing.sm,
  },
  progressBar: {
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.gray5,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 3,
    backgroundColor: colors.primary,
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
    paddingHorizontal: layout.screenPadding,
  },
  stockItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    marginBottom: spacing.sm,
    ...shadows.sm,
  },
  itemLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  checkCircle: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: colors.gray3,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  checkCircleActive: {
    backgroundColor: colors.success,
    borderColor: colors.success,
  },
  itemName: {
    ...typography.body,
    color: colors.text,
  },
  itemCategory: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  itemRight: {
    alignItems: 'flex-end',
  },
  systemQty: {
    ...typography.subhead,
    color: colors.textSecondary,
  },
  actualQty: {
    ...typography.caption1,
    color: colors.success,
    marginTop: 2,
  },
  qtyDiff: {
    color: colors.warning,
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

export default StocktakeScreen;
