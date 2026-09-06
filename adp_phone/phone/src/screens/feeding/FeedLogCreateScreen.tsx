import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, typography, spacing, borderRadius, layout } from '../../theme';
import { feedingApi } from '../../api/feeding';

type FeedLogCreateScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

const FeedLogCreateScreen: React.FC<FeedLogCreateScreenProps> = ({ navigation }) => {
  const [pondName, setPondName] = useState('');
  const [feedName, setFeedName] = useState('');
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');
  const [eatingStatus, setEatingStatus] = useState('normal');
  const [submitting, setSubmitting] = useState(false);

  const EATING_STATUS = [
    { key: 'normal', label: '正常', color: '#34C759' },
    { key: 'low', label: '少食', color: '#FF9500' },
    { key: 'refuse', label: '拒食', color: '#FF3B30' },
    { key: 'rush', label: '抢食', color: '#5AC8FA' },
  ];

  const handleSubmit = async () => {
    if (!pondName.trim()) {
      Alert.alert('提示', '请填写塘口');
      return;
    }
    if (!feedName.trim()) {
      Alert.alert('提示', '请填写饲料名称');
      return;
    }
    const numAmount = parseFloat(amount);
    if (!amount || isNaN(numAmount) || numAmount <= 0) {
      Alert.alert('提示', '请填写有效的投喂量');
      return;
    }
    try {
      setSubmitting(true);
      await feedingApi.createLog({
        pond_name: pondName.trim(),
        feed_name: feedName.trim(),
        actual_amount: numAmount,
        eating_status: eatingStatus,
        notes: notes.trim(),
        feed_time: new Date().toISOString(),
      });
      Alert.alert('成功', '投喂记录已保存', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('保存失败', err?.message || '请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>快速投喂记录</Text>
          <TouchableOpacity
            style={[styles.submitBtn, submitting && { opacity: 0.5 }]}
            onPress={handleSubmit}
            disabled={submitting}
          >
            {submitting ? (
              <ActivityIndicator size="small" color={colors.textInverse} />
            ) : (
              <Text style={styles.submitText}>保存</Text>
            )}
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={styles.form} showsVerticalScrollIndicator={false}>
          {/* Pond */}
          <Text style={styles.sectionTitle}>塘口</Text>
          <TextInput
            style={styles.input}
            placeholder="输入塘口名称"
            placeholderTextColor={colors.gray3}
            value={pondName}
            onChangeText={setPondName}
          />

          {/* Feed Type */}
          <Text style={styles.sectionTitle}>饲料名称</Text>
          <TextInput
            style={styles.input}
            placeholder="如：优质颗粒饲料"
            placeholderTextColor={colors.gray3}
            value={feedName}
            onChangeText={setFeedName}
          />

          {/* Amount */}
          <Text style={styles.sectionTitle}>投喂量 (kg)</Text>
          <TextInput
            style={styles.input}
            placeholder="0.0"
            placeholderTextColor={colors.gray3}
            value={amount}
            onChangeText={setAmount}
            keyboardType="decimal-pad"
          />

          {/* Eating Status */}
          <Text style={styles.sectionTitle}>摄食状态</Text>
          <View style={styles.statusRow}>
            {EATING_STATUS.map((s) => (
              <TouchableOpacity
                key={s.key}
                style={[
                  styles.statusChip,
                  eatingStatus === s.key && { backgroundColor: s.color + '20', borderColor: s.color },
                ]}
                onPress={() => setEatingStatus(s.key)}
              >
                <Text
                  style={[
                    styles.statusLabel,
                    eatingStatus === s.key && { color: s.color, fontWeight: '600' },
                  ]}
                >
                  {s.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Notes */}
          <Text style={styles.sectionTitle}>备注</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="天气、水温、异常情况..."
            placeholderTextColor={colors.gray3}
            value={notes}
            onChangeText={setNotes}
            multiline
            numberOfLines={3}
            textAlignVertical="top"
          />
        </ScrollView>
      </KeyboardAvoidingView>
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
  submitBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    minWidth: 60,
    alignItems: 'center',
  },
  submitText: {
    ...typography.subhead,
    color: colors.textInverse,
    fontWeight: '600',
  },
  form: {
    padding: layout.screenPadding,
    paddingBottom: spacing.xxl,
  },
  sectionTitle: {
    ...typography.subhead,
    color: colors.text,
    fontWeight: '600',
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  input: {
    backgroundColor: colors.backgroundSecondary,
    borderRadius: borderRadius.md,
    padding: spacing.base,
    ...typography.body,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.separatorLight,
  },
  textArea: {
    minHeight: 80,
    paddingTop: spacing.md,
  },
  statusRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  statusChip: {
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: colors.separatorLight,
    backgroundColor: colors.backgroundSecondary,
  },
  statusLabel: {
    ...typography.subhead,
    color: colors.textSecondary,
  },
});

export default FeedLogCreateScreen;
