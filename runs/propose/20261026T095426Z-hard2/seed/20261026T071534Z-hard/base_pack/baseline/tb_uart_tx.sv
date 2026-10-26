// Baseline testbench for uart_tx.
//
// Port of the upstream tests (alexforencich/verilog-uart @ 1b867e5):
//   tb/uart_tx/test_uart_tx.py  (cocotb): payload lengths 1..15 and 128,
//                                         incrementing and PRBS31 data
//   tb/test_uart_tx.py          (MyHDL):  two "walk" patterns
// Differences from upstream, on purpose:
//   - prescale = 5 (current upstream value); the line monitor samples at
//     exactly prescale*8 clocks per bit.
//   - cocotbext AxiStreamSource / UartSink replaced by small SV tasks.
// Like upstream, bytes within a payload are sent back-to-back over AXI-Stream.
`timescale 1ns / 1ps

module tb_uart_tx;

  localparam int CLK_PERIOD = 8;  // 125 MHz, as upstream
  localparam logic [15:0] PRESCALE = 16'd5;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic [7:0]  s_axis_tdata = '0;
  logic        s_axis_tvalid = 1'b0;
  logic [15:0] prescale = PRESCALE;
  wire         s_axis_tready;
  wire         txd;
  wire         busy;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart_tx #(.DATA_WIDTH(8)) dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .txd(txd),
    .busy(busy),
    .prescale(prescale)
  );

  // ---------------- line monitor + scoreboard ----------------
  byte unsigned expected[$];
  int unsigned  n_sent = 0, n_recv = 0;

  // All testbench driving/sampling happens on the falling edge, so DUT inputs
  // are stable at every rising edge (Verilator runs '<=' in initial blocks as
  // '=', so posedge-driven stimulus would race the DUT).
  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  // Decode 8N1 frames on txd: find the start edge, then sample mid-bit.
  initial begin
    forever begin
      byte unsigned b;
      int bit_clks;
      @(negedge txd);
      bit_clks = int'(prescale) * 8;
      wait_clks(bit_clks / 2);
      if (txd !== 1'b0) $fatal(1, "glitch: start bit not low at mid-bit");
      for (int i = 0; i < 8; i++) begin
        wait_clks(bit_clks);
        b[i] = txd;
      end
      wait_clks(bit_clks);
      if (txd !== 1'b1) $fatal(1, "missing stop bit");
      if (expected.size() == 0) $fatal(1, "unexpected byte 0x%02h", b);
      if (b !== expected[0])
        $fatal(1, "byte %0d: got 0x%02h, expected 0x%02h", n_recv, b, expected[0]);
      void'(expected.pop_front());
      n_recv++;
    end
  end

  // ---------------- stimulus helpers ----------------
  task automatic do_reset();
    rst = 1'b0; wait_clks(2);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(2);
  endtask

  // AXI-Stream transfer: hold tdata/tvalid until a clock edge with tready high.
  // Leaves tvalid asserted so the next byte follows back-to-back.
  task automatic axis_send(input byte unsigned b);
    bit ready;
    s_axis_tdata  = b;
    s_axis_tvalid = 1'b1;
    // tready is stable between falling and rising edge: sample it, then let
    // one rising edge pass. If it was high, the transfer happened on that edge.
    do begin
      ready = s_axis_tready;
      @(negedge clk);
    end while (!ready);
    expected.push_back(b);
    n_sent++;
  endtask

  task automatic send_and_check(input byte unsigned data[$]);
    foreach (data[i]) axis_send(data[i]);
    s_axis_tvalid = 1'b0;
    wait (n_recv == n_sent);
    #2000;  // 2 us gap between payloads, as upstream
  endtask

  // ---------------- payload generators (ported from upstream) ----------------
  function automatic void incrementing(input int len, output byte unsigned d[$]);
    d = {};
    for (int i = 0; i < len; i++) d.push_back(byte'(i % 256));
  endfunction

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
    do_reset();
    foreach (lengths[i]) begin incrementing(lengths[i], payload); send_and_check(payload); end
    do_reset();
    foreach (lengths[i]) begin prbs(lengths[i], payload); send_and_check(payload); end

    do_reset();
    send_and_check('{8'h00, 8'h01, 8'h02, 8'h04, 8'h08, 8'h10, 8'h20, 8'h40, 8'h80});
    send_and_check('{8'h00, 8'h01, 8'h03, 8'h07, 8'h0F, 8'h1F, 8'h3F, 8'h7F, 8'hFF});

    if (expected.size() != 0) $fatal(1, "%0d bytes never received", expected.size());
    $display("PASS tb_uart_tx: %0d bytes sent, %0d received", n_sent, n_recv);
    $finish;
  end

  initial begin
    #100ms;
    $fatal(1, "timeout");
  end

endmodule
