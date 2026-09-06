import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { warehouseApi } from '../../api/warehouse';
import { StockAlert } from '../../types';
import { colors, typography, spacing, borderRadius, layout } from '../../theme';
import { WarehouseStackParamList } from '../../navigation/WarehouseStack';

type StockAlertsScreenProps = {
  navigation: NativeStackNavigationProp<WarehouseStackParamList, 'StockAlerts'>;
};

const StockAlertsScreen: React.FC<StockAlertsScreenProps> = ({ navigation }) => {
  const [alerts, setAlerts] = useState<StockAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAlerts = useCallback(async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      const data = await warehouseApi.listAlerts();
      setAlerts(data);
    } catch (err) {
      console.warn('Failed to load alerts', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const getAlertIcon = (type: string): keyof typeof Ionicons.glyphMap => {
    switch (type) {
      case 'low_stock': return 'trending-down';
      case 'expired': return 'time-outline';
      case 'expiring': return 'alert-outline';
      default: return 'alert-circle';
    }
  };

  const getAlertColor = (type: string): string => {
    switch (type) {
      case 'low_stock': return colors.error;
      case 'expired': return colors.warning;
      case 'expiring': return colors.info;
      default: return colors.gray1;
    }
  };

  const getAlertLabel = (type: string): string => {
    switch (type) {
      case 'low_stock': return '库存不足';
      case 'expired': return '已过期';
      case 'expiring': return '即将过期';
      default: return '预警';
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>库存预警</Text>
        <View style={{ width: 36 }} />
      </View>

      {loading && alerts.length === 0 ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={alerts}
          keyExtractor={(item) => item.alert_key}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchAlerts(true)} tintColor={colors.primary} />
          }
          renderItem={({ item }) => (
            <View style={[styles.alertItem, item.status === 'pending' && styles.alertUnread]}>
              <View style={[styles.alertIcon, { backgroundColor: getAlertColor(item.alert_type) + '15' }]}>
                <Ionicons name={getAlertIcon(item.alert_type)} size={20} color={getAlertColor(item.alert_type)} />
              </View>
              <View style={styles.alertContent}>
                <Text style={styles.alertTitle}>{item.material_name}</Text>
                <Text style={styles.alertDetail}>
                  当前库存: {item.current_quantity} ({item.warehouse_name})
                </Text>
              </View>
              <View style={[styles.alertBadge, { backgroundColor: getAlertColor(item.alert_type) + '20' }]}>
                <Text style={[styles.alertBadgeText, { color: getAlertColor(item.alert_type) }]}>
                  {getAlertLabel(item.alert_type)}
                </Text>
              </View>
            </View>
          )}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="checkmark-circle-outline" size={48} color={colors.success} />
              <Text style={styles.emptyText}>暂无库存预警</Text>
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
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  backButton: {
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
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    padding: layout.screenPadding,
  },
  alertItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.base,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  alertUnread: {
    backgroundColor: colors.error + '03',
  },
  alertIcon: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  alertContent: {
    flex: 1,
    marginLeft: spacing.md,
  },
  alertTitle: {
    ...typography.body,
    color: colors.text,
    fontWeight: '500',
  },
  alertDetail: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginTop: 2,
  },
  alertTime: {
    ...typography.caption1,
    color: colors.gray2,
    marginTop: 2,
  },
  alertBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.full,
  },
  alertBadgeText: {
    ...typography.caption2,
    fontWeight: '600',
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

export default StockAlertsScreen;
