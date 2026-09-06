import React, { useState } from 'react';
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
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { Button, Input } from '../../components';
import { authApi } from '../../api/auth';
import { useAuth } from '../../hooks/useAuth';
import { colors, typography, spacing, borderRadius, layout } from '../../theme';
import { AuthStackParamList } from '../../navigation/AuthStack';

type PasswordChangeScreenProps = {
  navigation: NativeStackNavigationProp<AuthStackParamList, 'PasswordChange'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const PasswordChangeScreen: React.FC<PasswordChangeScreenProps> = ({ navigation }) => {
  const { refreshUser } = useAuth();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (!oldPassword) newErrors.oldPassword = '请输入当前密码';
    if (!newPassword) newErrors.newPassword = '请输入新密码';
    else if (newPassword.length < 6) newErrors.newPassword = '密码至少6位';
    if (newPassword !== confirmPassword) newErrors.confirmPassword = '两次输入的密码不一致';
    if (oldPassword === newPassword) newErrors.newPassword = '新密码不能与当前密码相同';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleChangePassword = async () => {
    if (!validate()) return;

    setLoading(true);
    try {
      await authApi.changePassword({
        current_password: oldPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      await refreshUser();
      Alert.alert('成功', '密码修改成功');
    } catch (error: any) {
      const message = error?.response?.data?.message || '修改密码失败，请稍后重试';
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
            <Text style={styles.title}>修改密码</Text>
            <Text style={styles.subtitle}>更新您的账户密码</Text>
          </View>

          <View style={styles.form}>
            <Input
              label="当前密码"
              placeholder="请输入当前密码"
              leftIcon="lock-closed-outline"
              value={oldPassword}
              onChangeText={setOldPassword}
              error={errors.oldPassword}
              isPassword
            />

            <Input
              label="新密码"
              placeholder="至少6位字符"
              leftIcon="lock-open-outline"
              value={newPassword}
              onChangeText={setNewPassword}
              error={errors.newPassword}
              isPassword
            />

            <Input
              label="确认新密码"
              placeholder="请再次输入新密码"
              leftIcon="lock-open-outline"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              error={errors.confirmPassword}
              isPassword
            />

            <Button
              title="确认修改"
              onPress={handleChangePassword}
              loading={loading}
              size="lg"
              style={styles.submitButton}
            />
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
  submitButton: {
    marginTop: spacing.lg,
  },
});

export default PasswordChangeScreen;
