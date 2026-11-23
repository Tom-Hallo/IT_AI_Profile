import assert from 'node:assert/strict';
import test from 'node:test';
import {installVietnameseFormValidation, vietnameseValidationMessage} from '../src/pixel-studio/form-validation.js';

function field(options = {}) {
  const {validity = {valid: false, valueMissing: true}, label = '', ...rest} = options;
  return {
    name: '',
    id: '',
    type: 'text',
    tagName: 'INPUT',
    labels: label ? [{textContent: label}] : [],
    validity,
    validationMessage: '',
    getAttribute: () => null,
    ...rest,
  };
}

test('thông báo Tiêu đề / JD và tên CV bằng tiếng Việt', () => {
  assert.equal(vietnameseValidationMessage(field({name: 'title'})), 'Vui lòng nhập tiêu đề.');
  assert.equal(vietnameseValidationMessage(field({name: 'jd'})), 'Vui lòng nhập mô tả công việc.');
  assert.equal(vietnameseValidationMessage(field({id: 'studio-title'})), 'Vui lòng nhập tên CV.');
  assert.equal(vietnameseValidationMessage(field({name: 'company', label: 'Công ty'})), 'Vui lòng nhập công ty.');
});

test('không nới lỏng checkbox đồng ý xử lý AI / phạm vi riêng tư', () => {
  assert.equal(
    vietnameseValidationMessage(field({type: 'checkbox', name: 'permit'})),
    'Vui lòng đồng ý xử lý nguồn đã chọn bằng AI trước khi tiếp tục.',
  );
  assert.equal(
    vietnameseValidationMessage(field({type: 'checkbox', label: 'Tôi đồng ý cấp quyền theo phạm vi trên'})),
    'Vui lòng đồng ý cấp quyền theo phạm vi đã chọn trước khi tiếp tục.',
  );
  assert.match(
    vietnameseValidationMessage(field({type: 'checkbox', name: 'agree', label: 'Cho phép AI xử lý dữ liệu'})),
    /đồng ý cho phép AI xử lý dữ liệu/,
  );
});

test('giữ thông báo setCustomValidity và Việt hóa các lỗi URL/email', () => {
  assert.equal(
    vietnameseValidationMessage(field({validity: {valid: false, customError: true}, validationMessage: 'Chỉ nhận URL HTTPS.'})),
    'Chỉ nhận URL HTTPS.',
  );
  assert.equal(
    vietnameseValidationMessage(field({type: 'url', validity: {valid: false, typeMismatch: true}})),
    'Vui lòng nhập đường dẫn URL hợp lệ.',
  );
  assert.equal(
    vietnameseValidationMessage(field({type: 'email', validity: {valid: false, typeMismatch: true}})),
    'Vui lòng nhập địa chỉ email hợp lệ.',
  );
});

test('invalid chặn tooltip nhưng không thay required, xóa lỗi khi input/change', () => {
  const before = {
    input: globalThis.HTMLInputElement,
    textarea: globalThis.HTMLTextAreaElement,
    select: globalThis.HTMLSelectElement,
  };
  class FakeControl {
    constructor() {
      this.name = 'permit';
      this.type = 'checkbox';
      this.id = '';
      this.tagName = 'INPUT';
      this.labels = [];
      this.validity = {valid: false, valueMissing: true};
      this.required = true;
      this.willValidate = true;
      this.attrs = new Map([['aria-describedby', 'existing-description']]);
      this.classes = new Set();
      this.classList = {
        add: value => this.classes.add(value),
        remove: value => this.classes.delete(value),
      };
    }
    getAttribute(name) { return this.attrs.get(name) ?? null; }
    setAttribute(name, value) { this.attrs.set(name, value); }
    removeAttribute(name) { this.attrs.delete(name); }
    insertAdjacentElement(_position, element) { element.isConnected = true; this.error = element; }
  }
  class FakeOther {}
  globalThis.HTMLInputElement = FakeControl;
  globalThis.HTMLTextAreaElement = FakeOther;
  globalThis.HTMLSelectElement = FakeOther;

  try {
    const events = new Map();
    const root = {
      addEventListener(type, listener) {
        if (!events.has(type)) events.set(type, []);
        events.get(type).push(listener);
      },
      createElement() {
        return {
          isConnected: false,
          setAttribute() {},
          remove() { this.isConnected = false; },
        };
      },
    };
    installVietnameseFormValidation(root);
    installVietnameseFormValidation(root); // không đăng ký trùng
    assert.equal(events.get('invalid').length, 1);

    const control = new FakeControl();
    let prevented = false;
    events.get('invalid')[0]({target: control, preventDefault() { prevented = true; }});
    assert.equal(prevented, true);
    assert.equal(control.required, true);
    assert.equal(control.validity.valid, false);
    assert.equal(control.error.textContent, 'Vui lòng đồng ý xử lý nguồn đã chọn bằng AI trước khi tiếp tục.');
    assert.equal(control.getAttribute('aria-invalid'), 'true');
    assert.match(control.getAttribute('aria-describedby'), /existing-description ita-field-validation-/);

    // Tích chọn xóa thông báo; việc hợp lệ hay không vẫn do HTML5 kiểm tra.
    events.get('change')[0]({target: control});
    assert.equal(control.getAttribute('aria-describedby'), 'existing-description');
    assert.equal(control.getAttribute('aria-invalid'), null);
    assert.equal(control.error.isConnected, false);
    assert.equal(control.required, true);
  } finally {
    globalThis.HTMLInputElement = before.input;
    globalThis.HTMLTextAreaElement = before.textarea;
    globalThis.HTMLSelectElement = before.select;
  }
});
