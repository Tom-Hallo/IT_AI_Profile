/**
 * Thông báo validation tiếng Việt cho các form HTML5 (kể cả modal được tạo động).
 * Không thay đổi required, validity, formnovalidate hoặc luồng submit hiện có.
 */

const requiredMessages = {
  permit: 'Vui lòng đồng ý xử lý nguồn đã chọn bằng AI trước khi tiếp tục.',
  agree: 'Vui lòng xác nhận đồng ý trước khi tiếp tục.',
  title: 'Vui lòng nhập tiêu đề.',
  jd: 'Vui lòng nhập mô tả công việc.',
  paths: 'Vui lòng nhập ít nhất một đường dẫn được phép.',
  evidence_url: 'Vui lòng nhập liên kết minh chứng.',
  query: 'Vui lòng nhập từ khóa tìm kiếm.',
};

function labelOf(control) {
  const label = control.labels?.[0];
  const text = control.getAttribute?.('aria-label') || label?.textContent || control.placeholder || '';
  return String(text).replace(/\s+/g, ' ').replace(/\s*[*：:]\s*$/, '').trim();
}

export function vietnameseValidationMessage(control) {
  const validity = control?.validity;
  if (!validity) return '';

  // Bảo toàn thông báo do nghiệp vụ tự đặt (ví dụ liên kết bằng chứng GitHub).
  if (validity.customError) {
    return control.validationMessage || 'Vui lòng kiểm tra lại thông tin này.';
  }

  const name = control.name || '';
  const id = control.id || '';
  const type = control.type || '';
  const label = labelOf(control);

  if (validity.valueMissing) {
    if (type === 'checkbox') {
      if (name === 'permit') return requiredMessages.permit;
      if (/phạm vi/i.test(label)) {
        return 'Vui lòng đồng ý cấp quyền theo phạm vi đã chọn trước khi tiếp tục.';
      }
      if (name === 'agree' && /AI|dữ liệu/i.test(label)) {
        return 'Vui lòng đồng ý cho phép AI xử lý dữ liệu trước khi tiếp tục.';
      }
      return label ? 'Vui lòng xác nhận "' + label + '" trước khi tiếp tục.' : requiredMessages.agree;
    }
    if (type === 'radio' || control.tagName === 'SELECT') {
      return 'Vui lòng chọn ' + (label || 'một tùy chọn') + '.';
    }
    if (type === 'file') return 'Vui lòng chọn tệp cần tải lên.';
    if (id === 'studio-title') return 'Vui lòng nhập tên CV.';
    if (id === 'studio-edit-title') return 'Vui lòng nhập tiêu đề bản CV.';
    if (id === 'studio-edit-body') return 'Vui lòng nhập nội dung CV.';
    if (id === 'studio-jd') return requiredMessages.jd;
    if (requiredMessages[name]) return requiredMessages[name];
    if (type === 'email') return 'Vui lòng nhập địa chỉ email.';
    return label ? 'Vui lòng nhập ' + label.toLocaleLowerCase('vi') + '.' : 'Vui lòng nhập thông tin bắt buộc.';
  }

  if (validity.typeMismatch) {
    if (type === 'email') return 'Vui lòng nhập địa chỉ email hợp lệ.';
    if (type === 'url') return 'Vui lòng nhập đường dẫn URL hợp lệ.';
  }
  if (validity.patternMismatch) return 'Thông tin chưa đúng định dạng yêu cầu.';
  if (validity.tooShort) return 'Nội dung quá ngắn. Vui lòng nhập thêm.';
  if (validity.tooLong) return 'Nội dung vượt quá số ký tự cho phép.';
  if (validity.rangeUnderflow) return 'Giá trị nhỏ hơn mức tối thiểu cho phép.';
  if (validity.rangeOverflow) return 'Giá trị lớn hơn mức tối đa cho phép.';
  if (validity.stepMismatch || validity.badInput) return 'Vui lòng nhập giá trị hợp lệ.';
  return 'Vui lòng kiểm tra lại thông tin này.';
}

/** Lắp listener một lần cho cả form hiện tại và các form được render về sau. */
export function installVietnameseFormValidation(root = document) {
  if (!root || root.__itaVietnameseValidationInstalled) return;
  root.__itaVietnameseValidationInstalled = true;

  const activeErrors = new WeakMap();
  let nextId = 0;
  const isControl = target =>
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement;

  function clearError(control) {
    const previous = activeErrors.get(control);
    if (!previous) return;
    previous.error.remove();
    const describedBy = (control.getAttribute('aria-describedby') || '')
      .split(/\s+/).filter(id => id && id !== previous.error.id);
    if (describedBy.length) control.setAttribute('aria-describedby', describedBy.join(' '));
    else control.removeAttribute('aria-describedby');
    if (previous.originalInvalid === null) control.removeAttribute('aria-invalid');
    else control.setAttribute('aria-invalid', previous.originalInvalid);
    control.classList.remove('ita-invalid-field');
    activeErrors.delete(control);
  }

  function showError(control) {
    if (!control.willValidate || control.validity.valid) return;
    let entry = activeErrors.get(control);
    if (!entry || !entry.error.isConnected) {
      const error = root.createElement('span');
      error.className = 'ita-field-validation';
      error.id = 'ita-field-validation-' + (++nextId);
      error.setAttribute('role', 'alert');
      error.setAttribute('aria-live', 'polite');
      const originalInvalid = control.getAttribute('aria-invalid');
      control.insertAdjacentElement('afterend', error);
      const describedBy = control.getAttribute('aria-describedby') || '';
      control.setAttribute('aria-describedby', [describedBy, error.id].filter(Boolean).join(' '));
      entry = {error, originalInvalid};
      activeErrors.set(control, entry);
    }
    entry.error.textContent = vietnameseValidationMessage(control);
    control.classList.add('ita-invalid-field');
    control.setAttribute('aria-invalid', 'true');
  }

  // Ngăn bubble/tooltip tiếng Anh, không ngăn HTML5 hủy submit khi invalid.
  root.addEventListener('invalid', event => {
    if (!isControl(event.target)) return;
    event.preventDefault();
    showError(event.target);
  }, true);

  // Cập nhật mượt mà: người dùng nhập/tích chọn là bỏ lỗi cũ ngay.
  for (const type of ['input', 'change']) {
    root.addEventListener(type, event => {
      if (isControl(event.target)) clearError(event.target);
    }, true);
  }

  // Form có nút disabled khi thiếu dữ liệu vẫn báo lỗi khi rời ô bắt buộc.
  root.addEventListener('focusout', event => {
    const control = event.target;
    if (!isControl(control) || control.type === 'checkbox' || control.type === 'radio') return;
    if (control.required && control.willValidate && control.validity.valueMissing) showError(control);
  }, true);
}
