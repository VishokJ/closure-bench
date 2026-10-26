// Baseline testbench for uart_rx.
//
// Port of the upstream tests (alexforencich/verilog-uart @ 1b867e5):
//   tb/uart_rx/test_uart_rx.py  (cocotb): payload lengths 1..15 and 128,
//                                         incrementing and PRBS31 data
//   tb/test_uart_rx.py          (MyHDL):  two "walk" patterns
// Differences from upstream, on purpose:
//   - prescale = 5 (current upstream value), bits driven at exactly
//     prescale*8 clocks (upstream's cocotb baud was ~4% off the DUT's rate).
//   - cocotbext UartSource / AxiStreamSink replaced by small SV tasks.
// Like upstream, the sink is always ready and every frame is well-formed.
`timescale 1ns / 1ps

module tb_uart_rx;

  localparam int CLK_PERIOD = 8;  // 125 MHz, as upstream
  localparam logic [15:0] PRESCALE = 16'd5;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = PRESCALE;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart_rx #(.DATA_WIDTH(8)) dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  // ---------------- scoreboard ----------------
  byte unsigned expected[$];
  int unsigned  n_sent = 0, n_recv = 0;

  always @(posedge clk) begin
    if (m_axis_tvalid && m_axis_tready) begin
      byte unsigned exp_b;
      if (expected.size() == 0) $fatal(1, "unexpected byte 0x%02h", m_axis_tdata);
      exp_b = expected.pop_front();
      if (m_axis_tdata !== exp_b)
        $fatal(1, "byte %0d: got 0x%02h, expected 0x%02h", n_recv, m_axis_tdata, exp_b);
      n_recv++;
    end
  end

  // ---------------- stimulus helpers ----------------
  // All testbench driving/sampling happens on the falling edge, so DUT inputs
  // are stable at every rising edge (Verilator runs '<=' in initial blocks as
  // '=', so posedge-driven stimulus would race the DUT).
  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic do_reset();
    rst = 1'b0; wait_clks(2);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(2);
  endtask

  // 8N1 frame on rxd, LSB first, each bit prescale*8 clocks.
  task automatic uart_send_byte(input byte unsigned b);
    int bit_clks = int'(prescale) * 8;
    expected.push_back(b);
    n_sent++;
    rxd = 1'b0;                   wait_clks(bit_clks);  // start
    for (int i = 0; i < 8; i++) begin
      rxd = b[i];                 wait_clks(bit_clks);
    end
    rxd = 1'b1;                   wait_clks(bit_clks);  // stop
  endtask

  task automatic send_and_check(input byte unsigned data[$]);
    foreach (data[i]) uart_send_byte(data[i]);
    wait (n_recv == n_sent);
    #2000;  // 2 us gap between payloads, as upstream
  endtask

  // ---------------- payload generators (ported from upstream) ----------------
  function automatic void incrementing(input int len, output byte unsigned d[$]);
    d = {};
    for (int i = 0; i < len; i++) d.push_back(byte'(i % 256));
  endfunction

  // Bit-exact port of upstream prbs31(); a fresh generator per payload.
  function automatic void prbs(input int len, output byte unsigned d[$]);
    int unsigned state = 32'h7fffffff;
    d = {};
    for (int n = 0; n < len; n++) begin
      for (int i = 0; i < 8; i++) begin
        if (((state & 32'h08000000) != 0) ^ ((state & 32'h40000000) != 0))
          state = ((state & 32'h3fffffff) << 1) | 1;
        else
          state = (state & 32'h3fffffff) << 1;
      end
      d.push_back(byte'(state & 32'hff));
    end
  endfunction

  // ---------------- test sequence ----------------
  int lengths[$] = '{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 128};
  byte unsigned payload[$];

  initial begin
    // cocotb suite: one test per data pattern, each starting from reset
    do_reset();
    foreach (lengths[i]) begin incrementing(lengths[i], payload); send_and_check(payload); end
    do_reset();
    foreach (lengths[i]) begin prbs(lengths[i], payload); send_and_check(payload); end

    // MyHDL suite
    do_reset();
    send_and_check('{8'h00, 8'h01, 8'h02, 8'h04, 8'h08, 8'h10, 8'h20, 8'h40, 8'h80});
    send_and_check('{8'h00, 8'h01, 8'h03, 8'h07, 8'h0F, 8'h1F, 8'h3F, 8'h7F, 8'hFF});

    if (expected.size() != 0) $fatal(1, "%0d bytes never received", expected.size());
    $display("PASS tb_uart_rx: %0d bytes sent, %0d received", n_sent, n_recv);
    $finish;
  end

  initial begin
    #100ms;
    $fatal(1, "timeout");
  end

endmodule
