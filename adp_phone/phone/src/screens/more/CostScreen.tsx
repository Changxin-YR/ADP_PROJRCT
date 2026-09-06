import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Card } from '../../components';
import { costApi } from '../../api/cost';
import { COST_CATEGORIES } from '../../types';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

type CostScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

const CATEGORY_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  pond_rent: 'home-outline',
  equipment: 'construct-outline',
  infrastructure: 'business-outline',
  labor: 'people-outline',
  electricity: 'flash-outline',
  seed: 'leaf-outline',
  feed: 'nutrition-outline',
  health: 'medical-outline',
  other: 'ellipsis-horizontal-outline',
};

const CATEGORY_COLORS: Record<string, string> = {
  pond_rent: '#007AFF',
  equipment: '#5AC8FA',
  infrastructure: '#AF52DE',
  labor: '#FF9500',
  electricity: '#FFCC00',
  seed: '#34C759',
  feed: '#FF3B30',
  health: '#FF2D55',
  other: '#8E8E93',
};

const CATEGORY_NAMES: Record<string, string> = {
  pond_rent: '塘租',
  equipment: '设备',
  infrastructure: '基建',
  labor: '人工',
  electricity: '电费',
  seed: '苗种',
  feed: '饲料',
  health: '动保',
  other: '其他',
};

const CostScreen: React.FC<CostScreenProps> = ({ navigation }) => {
  const [period, setPeriod] = useState<'month' | 'quarter' | 'year'>('month');
  const [structure, setStructure] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const getPeriodRange = useCallback(() => {
    const now = new Date();
    let start: string;
    let end: string;
    if (period === 'month') {
      start = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
      const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
      end = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${lastDay}`;
    } else if (period === 'quarter') {
      const qStart = Math.floor(now.getMonth() / 3) * 3;
      start = `${now.getFullYear()}-${String(qStart + 1).padStart(2, '0')}-01`;
      const qEnd = new Date(now.getFullYear(), qStart + 3, 0);
      end = `${qEnd.getFullYear()}-${String(qEnd.getMonth() + 1).padStart(2, '0')}-${qEnd.getDate()}`;
    } else {
      start = `${now.getFullYear()}-01-01`;
      end = `${now.getFullYear()}-12-31`;
    }
    return { start, end };
  }, [period]);

  const fetchStructure = useCallback(async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      const { start, end } = getPeriodRange();
      const data = await costApi.getStructure(start, end);
      setStructure(data);
    } catch (err) {
      console.warn('Failed to load cost structure', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [getPeriodRange]);

  useEffect(() => {
    fetchStructure();
  }, [fetchStructure]);

  const totalCost = structure?.categories?.reduce(
    (sum: number, c: any) => sum + (c.total_amount || 0), 0
  ) || 0;

  const categories = structure?.categories || COST_CATEGORIES.map(c => ({
    category_code: c.code,
    category_name: c.name,
    total_amount: 0,
  }));

  const periodLabel = () => {
    const now = new Date();
    if (period === 'month') return `${now.getFullYear()}年${now.getMonth() + 1}月`;
    if (period === 'quarter') return `${now.getFullYear()}年第${Math.floor(now.getMonth() / 3) + 1}季度`;
    return `${now.getFullYear()}年`;
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>成本核算</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => fetchStructure(true)} tintColor={colors.primary} />
        }
      >
        {/* Period Selector */}
        <View style={styles.periodRow}>
          {(['month', 'quarter', 'year'] as const).map((p) => (
            <TouchableOpacity
              key={p}
              style={[styles.periodBtn, period === p && styles.periodBtnActive]}
              onPress={() => setPeriod(p)}
            >
              <Text style={[styles.periodText, period === p && styles.periodTextActive]}>
                {p === 'month' ? '月度' : p === 'quarter' ? '季度' : '年度'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Total Card */}
        <Card style={styles.totalCard}>
          {loading ? (
            <ActivityIndicator size="small" color={colors.primary} />
          ) : (
            <>
              <Text style={styles.totalLabel}>总成本</Text>
              <Text style={styles.totalAmount}>
                ¥{totalCost.toLocaleString()}
              </Text>
              <Text style={styles.totalPeriod}>{periodLabel()}</Text>
            </>
          )}
        </Card>

        {/* Categories */}
        <Text style={styles.sectionTitle}>成本构成（九维度）</Text>
        {categories.map((cat: any, index: number) => {
          const code = cat.category_code || cat.code;
          const name = CATEGORY_NAMES[code] || cat.category_name || cat.name;
          const amount = cat.total_amount || 0;
          const percentage = totalCost > 0 ? Math.round((amount / totalCost) * 100) : 0;
          const catColor = CATEGORY_COLORS[code] || '#8E8E93';
          const catIcon = CATEGORY_ICONS[code] || 'ellipsis-horizontal-outline';

          return (
            <TouchableOpacity key={index} style={styles.categoryItem} activeOpacity={0.7}>
              <View style={[styles.catIcon, { backgroundColor: catColor + '15' }]}>
                <Ionicons name={catIcon} size={20} color={catColor} />
              </View>
              <View style={styles.catContent}>
                <View style={styles.catHeader}>
                  <Text style={styles.catName}>{name}</Text>
                  <Text style={styles.catAmount}>¥{amount.toLocaleString()}</Text>
                </View>
                <View style={styles.barContainer}>
                  <View style={[styles.bar, { width: `${percentage}%`, backgroundColor: catColor }]} />
                </View>
                <Text style={styles.catPercentage}>{percentage}%</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
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
    textAlign: 'center',
  },
  scrollContent: {
    padding: layout.screenPadding,
    paddingTop: 0,
  },
  periodRow: {
    flexDirection: 'row',
    backgroundColor: colors.background,
    borderRadius: borderRadius.md,
    padding: 3,
    marginBottom: spacing.lg,
  },
  periodBtn: {
    flex: 1,
    paddingVertical: spacing.sm,
    alignItems: 'center',
    borderRadius: borderRadius.sm,
  },
  periodBtnActive: {
    backgroundColor: colors.primary,
    ...shadows.sm,
  },
  periodText: {
    ...typography.subhead,
    color: colors.textTertiary,
    fontWeight: '500',
  },
  periodTextActive: {
    color: colors.textInverse,
    fontWeight: '600',
  },
  totalCard: {
    alignItems: 'center',
    paddingVertical: spacing.xl,
    marginBottom: spacing.xl,
  },
  totalLabel: {
    ...typography.subhead,
    color: colors.textTertiary,
  },
  totalAmount: {
    ...typography.largeTitle,
    color: colors.text,
    marginTop: spacing.xs,
  },
  totalPeriod: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: spacing.xs,
  },
  sectionTitle: {
    ...typography.headline,
    color: colors.text,
    marginBottom: spacing.md,
  },
  categoryItem: {
    flexDirection: 'row',
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    marginBottom: spacing.sm,
    ...shadows.sm,
  },
  catIcon: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  catContent: {
    flex: 1,
  },
  catHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  catName: {
    ...typography.body,
    color: colors.text,
  },
  catAmount: {
    ...typography.headline,
    color: colors.text,
  },
  barContainer: {
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.gray5,
    overflow: 'hidden',
  },
  bar: {
    height: '100%',
    borderRadius: 3,
  },
  catPercentage: {
    ...typography.caption2,
    color: colors.textTertiary,
    marginTop: 4,
  },
});

export default CostScreen;
