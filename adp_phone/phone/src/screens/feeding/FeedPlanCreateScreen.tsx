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
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';
import { feedingApi } from '../../api/feeding';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const FeedPlanCreateScreen: React.FC<Props> = ({ navigation }) => {
  const [name, setName] = useState('');
  const [pondName, setPondName] = useState('');
  const [feedName, setFeedName] = useState('');
  const [dailyAmount, setDailyAmount] = useState('');
  const [frequency, setFrequency] = useState('2');
  const [startDate, setStartDate] = useState(new Date().toISOString().split('T')[0]);
  const [endDate, setEndDate] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim()) {
      Alert.alert('提示', '请填写计划名称');
      return;
    }
    if (!pondName.trim()) {
      Alert.alert('提示', '请填写塘口');
      return;
    }
    if (!feedName.trim()) {
      Alert.alert('提示', '请填写饲料名称');
      return;
    }
    if (!dailyAmount.trim() || isNaN(Number(dailyAmount))) {
      Alert.alert('提示', '请填写有效的日投喂量');
      return;
    }
    try {
      setSubmitting(true);
      await feedingApi.createPlan({
        name: name.trim(),
        pond_name: pondName.trim(),
        feed_name: feedName.trim(),
        daily_amount: Number(dailyAmount),
        frequency: Number(frequency),
        start_date: startDate,
        end_date: endDate || undefined,
        notes: notes.trim() || undefined,
      });
      Alert.alert('成功', '喂养计划已创建', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('创建失败', err?.message || '请稍后重试');
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
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>新建喂养计划</Text>
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
          <Text style={styles.label}>计划名称 *</Text>
          <TextInput
            style={styles.input}
            placeholder="如：1号塘鲈鱼6月投喂计划"
            placeholderTextColor={colors.gray3}
            value={name}
            onChangeText={setName}
          />

          <Text style={styles.label}>塘口 *</Text>
          <TextInput
            style={styles.input}
            placeholder="输入塘口名称"
            placeholderTextColor={colors.gray3}
            value={pondName}
            onChangeText={setPondName}
          />

          <Text style={styles.label}>饲料名称 *</Text>
          <TextInput
            style={styles.input}
            placeholder="输入饲料名称"
            placeholderTextColor={colors.gray3}
            value={feedName}
            onChangeText={setFeedName}
          />

          <View style={styles.row}>
            <View style={styles.halfField}>
              <Text style={styles.label}>日投喂量(kg) *</Text>
              <TextInput
                style={styles.input}
                placeholder="0.0"
                placeholderTextColor={colors.gray3}
                value={dailyAmount}
                onChangeText={setDailyAmount}
                keyboardType="decimal-pad"
              />
            </View>
            <View style={styles.halfField}>
              <Text style={styles.label}>每日次数</Text>
              <TextInput
                style={styles.input}
                placeholder="2"
                placeholderTextColor={colors.gray3}
                value={frequency}
                onChangeText={setFrequency}
                keyboardType="number-pad"
              />
            </View>
          </View>

          <View style={styles.row}>
            <View style={styles.halfField}>
              <Text style={styles.label}>开始日期</Text>
              <TextInput
                style={styles.input}
                placeholder="YYYY-MM-DD"
                placeholderTextColor={colors.gray3}
                value={startDate}
                onChangeText={setStartDate}
              />
            </View>
            <View style={styles.halfField}>
              <Text style={styles.label}>结束日期</Text>
              <TextInput
                style={styles.input}
                placeholder="YYYY-MM-DD"
                placeholderTextColor={colors.gray3}
                value={endDate}
                onChangeText={setEndDate}
              />
            </View>
          </View>

          <Text style={styles.label}>备注</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="注意事项、投喂标准..."
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
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: layout.screenPadding, paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separatorLight },
  backBtn: { width: 36, height: 36, borderRadius: borderRadius.full, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { ...typography.headline, color: colors.text, flex: 1, textAlign: 'center' },
  submitBtn: { backgroundColor: colors.primary, paddingHorizontal: spacing.base, paddingVertical: spacing.sm, borderRadius: borderRadius.md, minWidth: 60, alignItems: 'center' },
  submitText: { ...typography.subhead, color: colors.textInverse, fontWeight: '600' },
  form: { padding: layout.screenPadding, paddingBottom: spacing.xxl },
  label: { ...typography.subhead, color: colors.text, fontWeight: '600', marginTop: spacing.lg, marginBottom: spacing.sm },
  input: { backgroundColor: colors.backgroundSecondary, borderRadius: borderRadius.md, padding: spacing.base, ...typography.body, color: colors.text, borderWidth: 1, borderColor: colors.separatorLight },
  textArea: { minHeight: 80, paddingTop: spacing.md },
  row: { flexDirection: 'row', gap: spacing.md },
  halfField: { flex: 1 },
});

export default FeedPlanCreateScreen;
