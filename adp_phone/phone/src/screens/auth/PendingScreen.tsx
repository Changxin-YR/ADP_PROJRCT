import React, { useCallback, useEffect, useState } from 'react';
import { Alert, SafeAreaView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Button } from '../../components';
import { useAuth } from '../../hooks/useAuth';
import { authApi } from '../../api/auth';
import { colors, layout, spacing, typography } from '../../theme';

const PendingScreen: React.FC = () => {
  const { user, logout, refreshUser } = useAuth();
  const [application, setApplication] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setApplication((await authApi.getApplication()).application);
      await refreshUser();
    } catch {
      Alert.alert('读取失败', '暂时无法读取申请状态，请稍后重试。');
    } finally {
      setLoading(false);
    }
  }, [refreshUser]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const rejected = user?.status === 'rejected';
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Ionicons name={rejected ? 'close-circle-outline' : 'time-outline'} size={72} color={rejected ? colors.error : colors.primary} />
        <Text style={styles.title}>{rejected ? '注册申请未通过' : '注册申请审核中'}</Text>
        <Text style={styles.message}>
          {rejected ? '请联系管理员了解原因，并按要求重新提交。' : '管理员审批通过后即可进入业务工作区。'}
        </Text>
        {application && (
          <View style={styles.details}>
            <Text style={styles.detail}>申请人：{String(application.name || user?.name || '')}</Text>
            <Text style={styles.detail}>状态：{String(application.status || (rejected ? 'rejected' : 'pending'))}</Text>
            {!!application.application_note && <Text style={styles.detail}>说明：{String(application.application_note)}</Text>}
          </View>
        )}
        <Button title="刷新申请状态" onPress={refresh} loading={loading} size="lg" style={styles.button} />
        <Button title="退出账号" onPress={logout} variant="secondary" size="lg" />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: layout.screenPadding },
  title: { ...typography.title1, color: colors.text, marginTop: spacing.lg, textAlign: 'center' },
  message: { ...typography.body, color: colors.textSecondary, marginTop: spacing.sm, textAlign: 'center' },
  details: { width: '100%', backgroundColor: colors.backgroundSecondary, padding: spacing.base, marginTop: spacing.xl },
  detail: { ...typography.subhead, color: colors.textSecondary, marginBottom: spacing.xs },
  button: { width: '100%', marginTop: spacing.xl, marginBottom: spacing.md },
});

export default PendingScreen;
