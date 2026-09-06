import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  TouchableOpacity,
  Alert,
  Dimensions,
  ActivityIndicator,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { Button, Input } from '../../components';
import Select from '../../components/forms/Select';
import { authApi } from '../../api/auth';
import { RegistrationOptions } from '../../types';
import { useAuth } from '../../hooks/useAuth';
import { colors, typography, spacing, borderRadius, layout } from '../../theme';
import { AuthStackParamList } from '../../navigation/AuthStack';

type RegisterScreenProps = {
  navigation: NativeStackNavigationProp<AuthStackParamList, 'Register'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const RegisterScreen: React.FC<RegisterScreenProps> = ({ navigation }) => {
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [roleId, setRoleId] = useState('');
  const [scopeType, setScopeType] = useState<'farm' | 'area' | 'personal'>('area');
  const [areaId, setAreaId] = useState('');
  const [applicationNote, setApplicationNote] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [options, setOptions] = useState<RegistrationOptions | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    authApi.getRegistrationOptions()
      .then((data) => {
        setOptions(data);
        if (data.roles[0]) setRoleId(String(data.roles[0].id));
        if (data.areas[0]) setAreaId(String(data.areas[0].id));
      })
      .catch(() => Alert.alert('读取失败', '暂时无法读取注册选项，请稍后重试。'))
      .finally(() => setOptionsLoading(false));
  }, []);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (!name.trim()) newErrors.name = '请输入姓名';
    if (!/^1\d{10}$/.test(phone.replace(/[-\s]/g, ''))) newErrors.phone = '请输入有效手机号';
    if (!roleId) newErrors.roleId = '请选择申请岗位';
    if (!areaId) newErrors.areaId = '请选择所属区域';
    if (!password) newErrors.password = '请输入密码';
    else if (password.length < 6) newErrors.password = '密码至少6个字符';
    if (password !== confirmPassword) newErrors.confirmPassword = '两次密码不一致';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleRegister = async () => {
    if (!validate()) return;

    setLoading(true);
    try {
      const result = await register({
        name: name.trim(),
        phone: phone.replace(/[-\s]/g, ''),
        password,
        confirm_password: confirmPassword,
        desired_role_id: Number(roleId),
        desired_scope_type: scopeType,
        area_id: Number(areaId),
        application_note: applicationNote.trim(),
      });
      if (result.status === 'pending') Alert.alert('申请已提交', '请等待管理员审批。');
    } catch (error: any) {
      const message = error?.response?.data?.message || '注册失败，请稍后重试';
      Alert.alert('错误', message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.content}>
          <View style={styles.header}>
            <TouchableOpacity
              onPress={() => navigation.goBack()}
              style={styles.backButton}
            >
              <Ionicons name="arrow-back" size={24} color={colors.text} />
            </TouchableOpacity>
            <Text style={styles.title}>创建账号</Text>
            <Text style={styles.subtitle}>加入水产养殖管理平台</Text>
          </View>

          <View style={styles.form}>
            <Input
              label="姓名"
              placeholder="请输入真实姓名"
              leftIcon="person-outline"
              value={name}
              onChangeText={setName}
              error={errors.name}
            />

            <Input
              label="手机号"
              placeholder="请输入手机号"
              leftIcon="call-outline"
              value={phone}
              onChangeText={setPhone}
              error={errors.phone}
              keyboardType="phone-pad"
            />

            {optionsLoading ? <ActivityIndicator color={colors.primary} style={styles.optionsLoading} /> : (
              <>
                <Select
                  label="申请岗位"
                  placeholder="请选择申请岗位"
                  required
                  value={roleId}
                  options={(options?.roles || []).map((role) => ({ label: role.name, value: String(role.id) }))}
                  onSelect={setRoleId}
                  error={errors.roleId}
                />
                <Select
                  label="数据范围"
                  required
                  value={scopeType}
                  options={[{ label: '区域数据', value: 'area' }, { label: '全场数据', value: 'farm' }, { label: '仅本人数据', value: 'personal' }]}
                  onSelect={(value) => setScopeType(value as typeof scopeType)}
                />
                <Select
                  label="所属区域"
                  placeholder="请选择所属区域"
                  required
                  value={areaId}
                  options={(options?.areas || []).map((area) => ({ label: area.name, value: String(area.id) }))}
                  onSelect={setAreaId}
                  error={errors.areaId}
                />
              </>
            )}

            <Input
              label="申请说明（选填）"
              placeholder="请说明申请原因或负责范围"
              leftIcon="document-text-outline"
              value={applicationNote}
              onChangeText={setApplicationNote}
              multiline
              numberOfLines={3}
              style={styles.noteInput}
            />

            <Input
              label="密码"
              placeholder="至少6个字符"
              leftIcon="lock-closed-outline"
              value={password}
              onChangeText={setPassword}
              error={errors.password}
              isPassword
            />

            <Input
              label="确认密码"
              placeholder="请再次输入密码"
              leftIcon="lock-closed-outline"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              error={errors.confirmPassword}
              isPassword
            />

            <Button
              title="注册"
              onPress={handleRegister}
              loading={loading}
              size="lg"
              style={styles.registerButton}
            />

            <View style={styles.footer}>
              <Text style={styles.footerText}>已有账号？</Text>
              <TouchableOpacity onPress={() => navigation.goBack()}>
                <Text style={styles.footerLink}>立即登录</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContent: {
    flexGrow: 1,
  },
  content: {
    flex: 1,
    paddingHorizontal: layout.screenPadding,
    paddingTop: Platform.OS === 'ios' ? 60 : 40,
    maxWidth: isTablet ? 480 : undefined,
    alignSelf: 'center',
    width: '100%',
  },
  header: {
    marginBottom: spacing.xxl,
  },
  backButton: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.full,
    backgroundColor: colors.backgroundSecondary,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  title: {
    ...typography.largeTitle,
    color: colors.text,
    marginBottom: spacing.xs,
  },
  subtitle: {
    ...typography.subhead,
    color: colors.textTertiary,
  },
  form: {
    width: '100%',
  },
  registerButton: {
    marginTop: spacing.lg,
  },
  optionsLoading: {
    marginVertical: spacing.md,
  },
  noteInput: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: spacing.xl,
    paddingBottom: spacing.xxl,
  },
  footerText: {
    ...typography.subhead,
    color: colors.textTertiary,
  },
  footerLink: {
    ...typography.subhead,
    color: colors.primary,
    fontWeight: '600',
  },
});

export default RegisterScreen;
