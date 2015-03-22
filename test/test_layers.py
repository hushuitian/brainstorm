#!/usr/bin/env python
# coding=utf-8

from __future__ import division, print_function, unicode_literals
from brainstorm.structure.buffer_views import BufferView
import pytest
from brainstorm.layers.python_layers import FeedForwardLayer
from brainstorm.handlers import NumpyHandler
import numpy as np
np.random.seed()


def approx_fprime(xk, f, epsilon, *args):
    f0 = f(*((xk,)+args))
    grad = np.zeros((len(xk),), float)
    ei = np.zeros((len(xk),), float)
    for k in range(len(xk)):
        ei[k] = epsilon
        grad[k] = (f(*((xk+ei,)+args)) - f0)/epsilon
        ei[k] = 0.0
    return grad


def get_output_error(_h, forward_buffers):
    error = 0.0
    for key in forward_buffers.outputs.keys():
        value = _h.get_numpy_copy(forward_buffers.outputs[key])
        error += 0.5*(value**2).sum()
    return error


def setup_buffers(time_steps, num, layer):
    _h = layer.handler
    forward_buffer_names = []
    forward_buffer_views = []
    backward_buffer_names = []
    backward_buffer_views = []

    # setup inputs
    input_names = layer.input_names
    forward_input_buffers = []
    backward_input_buffers = []

    print("Setting up inputs")
    assert set(input_names) == set(layer.in_shapes.keys())
    for name in input_names:
        shape = layer.in_shapes[name]
        print(name, " : ", (time_steps, num) + shape)
        data = _h.zeros((time_steps, num) + shape)
        _h.set_from_numpy(data, np.random.randn(*(time_steps, num) + shape))
        forward_input_buffers.append(data)
        backward_input_buffers.append(_h.zeros((time_steps, num) + shape))

    forward_buffer_names.append('inputs')
    forward_buffer_views.append(BufferView(input_names, forward_input_buffers))
    backward_buffer_names.append('inputs')
    backward_buffer_views.append(BufferView(input_names,
                                            backward_input_buffers))

    # setup outputs
    output_names = layer.output_names
    forward_output_buffers = []
    backward_output_buffers = []

    print("Setting up outputs")
    assert set(output_names) == set(layer.in_shapes.keys())
    for name in output_names:
        shape = layer.out_shapes[name]
        print(name, " : ", (time_steps, num) + shape)
        forward_output_buffers.append(_h.zeros((time_steps, num) + shape))
        backward_output_buffers.append(_h.zeros((time_steps, num) + shape))

    forward_buffer_names.append('outputs')
    forward_buffer_views.append(BufferView(output_names,
                                           forward_output_buffers))
    backward_buffer_names.append('outputs')
    backward_buffer_views.append(BufferView(output_names,
                                            backward_output_buffers))

    # setup parameters
    param_names = []
    forward_param_buffers = []
    backward_param_buffers = []

    param_structure = layer.get_parameter_structure()
    print("Setting up parameters")
    for name, attributes in sorted(param_structure.items(),
                                   key=lambda x: x[1]['index']):
        param_names.append(name)
        print(name, " : ", attributes['shape'])
        data = _h.zeros(attributes['shape'])
        _h.set_from_numpy(data, np.random.randn(*attributes['shape']))
        forward_param_buffers.append(data)
        backward_param_buffers.append(_h.zeros(attributes['shape']))

    forward_buffer_names.append('parameters')
    forward_buffer_views.append(BufferView(param_names, forward_param_buffers))
    backward_buffer_names.append('parameters')
    backward_buffer_views.append(BufferView(param_names, backward_param_buffers))

    # setup internals
    internal_names = []
    forward_internal_buffers = []
    backward_internal_buffers = []

    internal_structure = layer.get_internal_structure()
    print("Setting up internals")
    for name, attributes in sorted(internal_structure.items(),
                                   key=lambda x: x[1]['index']):
        print(name, attributes)
        internal_names.append(name)
        print(name, " : ", attributes['shape'])
        forward_internal_buffers.append(_h.zeros((time_steps, num) +
                                                attributes['shape']))
        backward_internal_buffers.append(_h.zeros((time_steps, num) +
                                                 attributes['shape']))

    forward_buffer_names.append('internals')
    forward_buffer_views.append(BufferView(internal_names,
                                           forward_internal_buffers))
    backward_buffer_names.append('internals')
    backward_buffer_views.append(BufferView(internal_names,
                                            backward_internal_buffers))

    # Finally, setup forward and backward buffers
    forward_buffers = BufferView(forward_buffer_names, forward_buffer_views)
    backward_buffers = BufferView(backward_buffer_names, backward_buffer_views)
    return forward_buffers, backward_buffers


def test_fully_connected_layer():

    eps = 1e-4
    time_steps = 3
    num = 2
    input_shape = 3
    layer_shape = 2

    in_shapes = {'default': (input_shape,)}
    layer = FeedForwardLayer(in_shapes, [], [], shape=layer_shape,
                             activation_function='sigmoid')
    layer.set_handler(NumpyHandler(np.float64))
    print("\n---------- Testing FullyConnectedLayer ----------")
    _h = layer.handler
    forward_buffers, backward_buffers = setup_buffers(time_steps, num, layer)
    layer.forward_pass(forward_buffers)
    for key in forward_buffers.outputs.keys():
        _h.copy_to(backward_buffers.outputs[key], forward_buffers.outputs[key])
    layer.backward_pass(forward_buffers, backward_buffers)

    for key in forward_buffers.parameters.keys():
        print("\nChecking parameter: ", key)
        view = forward_buffers.parameters[key]
        size = _h.size(forward_buffers.parameters[key])
        x0 = _h.get_numpy_copy(view).reshape((size,))
        grad_calc = _h.get_numpy_copy(backward_buffers.parameters[
            key]).reshape((size,))
        print("x0: ", x0)
        print("Expected grad: ", grad_calc)

        def f(x):
            flat_view = _h.reshape(view, (size,))
            _h.set_from_numpy(flat_view, x)
            layer.forward_pass(forward_buffers)
            _h.set_from_numpy(flat_view, x0)
            return get_output_error(_h, forward_buffers)

        grad_approx = approx_fprime(x0, f, eps)
        print("Approx grad:", grad_approx)
        assert np.allclose(grad_approx, grad_calc, rtol=0.0, atol=1e-4)

    for key in forward_buffers.inputs.keys():
        print("\nChecking input: ", key)
        view = forward_buffers.inputs[key]
        size = _h.size(forward_buffers.inputs[key])
        x0 = _h.get_numpy_copy(view).reshape((size,))
        grad_calc = _h.get_numpy_copy(backward_buffers.inputs[
            key]).reshape((size,))
        print("x0: ", x0)
        print("Expected grad: ", grad_calc)

        def f(x):
            flat_view = _h.reshape(view, (size,))
            _h.set_from_numpy(flat_view, x)
            layer.forward_pass(forward_buffers)
            _h.set_from_numpy(flat_view, x0)
            return get_output_error(_h, forward_buffers)

        grad_approx = approx_fprime(x0, f, eps)
        print("Approx grad:", grad_approx)
        assert np.allclose(grad_approx, grad_calc, rtol=0.0, atol=1e-4)
